# Example 3 — Extract entities from 200 emails (batch pre-agency, Clause 4)

## Task

> For each of 200 archived support emails in `~/archive/support/*.eml`, extract: customer name, product mentioned, sentiment (positive/neutral/negative), and the single most important sentence verbatim. Collect all results into one JSONL file.

## Walking the rubric

- **Clause 1 — file discovery?** No. The human can produce the file list (`ls ~/archive/support/*.eml`) and feed each path in. The CLI does not need to traverse anything.
- **Clause 2 — iterative refinement against ground truth?** No. There's no test that says "the extraction is right." Quality is judged downstream.
- **Clause 3 — one transform on a known input?** Almost — but it's not one input, it's 200.
- **Clause 4 — batch shape?** **Yes, fires.** Same transform per email, results joined into one file. Per-email work is independent.

Stop. Class is `pre-agency`.

## Substrate pick

From an installed inventory of `llm,aichat,claude,codex,opencode`, the chosen CLI is **`llm`**:

- Single-shot, structured-output mode (`llm --schema` or just a strict JSON-only system prompt).
- Composes trivially with `xargs -P` for parallelism.
- Logs each call to its SQLite store, so re-costing 200 calls is one query.

## What the prompt would emit

```json
{
  "class": "pre-agency",
  "cli": "llm",
  "clause_fired": 4,
  "clause_evidence": "for each of 200 emails, extract 4 fields — same transform applied independently across N inputs",
  "confidence": "high",
  "note": "human enumerates the file list; each per-email call is independent"
}
```

## Mismatch shape we're avoiding

If we reached for an agent CLI ("just fan out 200 `claude` calls"):

- Each agent boots its tool registry (file read, file write, bash) — overhead we don't need.
- Each agent gets a fresh prompt-cache prefix, so we burn cache-miss tokens 200 times instead of reusing one cached system prompt.
- Logs are 200 nested traces with 1 turn each. Re-costing is painful; auditing is painful.
- Cost easily runs 5–15× the pre-agency batch.

This is the **batch-as-agent-fleet** failure mode from the README. The smell is when "let me just parallelize my agent CLI" feels like the right move for a one-transform-per-input task.

## Concrete invocation

```bash
# Sequential (slow but simple)
ls ~/archive/support/*.eml | while read -r f; do
  cat "$f" | llm -m gpt-4o-mini -s "$(cat <<'EOF'
Extract from this email and emit one JSON object on a single line:
{"customer": "...", "product": "...", "sentiment": "positive|neutral|negative", "key_sentence": "..."}
- customer: full name from the From header or sign-off; if absent, "unknown"
- product: the product name they're asking about; if multiple, the most prominent
- sentiment: one of the three; default neutral when ambiguous
- key_sentence: copy verbatim from the email body, the single sentence that most carries their intent
Emit JSON only. No prose. No code fences.
EOF
)"
done > extractions.jsonl

# Parallel (faster, same shape)
ls ~/archive/support/*.eml | xargs -P 8 -I {} sh -c '
  cat "$1" | llm -m gpt-4o-mini -s "..."
' _ {} > extractions.jsonl
```

Two hundred independent transforms, joined by shell redirection. Cache-prefix reuse is automatic when the system prompt is identical across calls. Task class matches substrate class.

## Where this would shift to agent

If the requirement changed to "and re-extract any record whose `sentiment` doesn't agree with a sentiment-classifier baseline within tolerance," that adds Clause 2 (refinement against ground truth) for a subset. The right shape becomes a two-pass plan:

1. Pass 1: this batch pre-agency extraction.
2. Pass 2: agent CLI invoked only for the records that fail tolerance, with tool access to re-read the source `.eml` and the baseline output.

That split is exactly what the rubric's Clause 2 + Clause 4 tiebreaker prescribes.
