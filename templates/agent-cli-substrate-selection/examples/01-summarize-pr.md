# Example 1 — Summarize a PR diff (pre-agency, Clause 3)

## Task

> Read the diff for PR #1234 in the `acme/widgets` repo and produce a 5-bullet summary covering: scope, risk, test coverage, suggested reviewers, and one open question.

## Walking the rubric

- **Clause 1 — file discovery?** No. The input is one named PR diff. The human will produce it (e.g. `gh pr diff 1234`) and pipe it in. No filesystem traversal required from the CLI.
- **Clause 2 — iterative refinement against ground truth?** No. There is no test to run, no build to react to. The output is a textual summary; success is judged by the reader.
- **Clause 3 — one transform on a known input?** **Yes, fires.** One input (the diff), one transformation (summarize into 5 bullets), output flows downstream (clipboard, Slack, the reviewer's eyes).

Stop. Class is `pre-agency`.

## Substrate pick

From an installed inventory of `llm,aichat,claude,codex,opencode`, the chosen CLI is **`llm`**:

- It accepts the diff on stdin.
- It runs one model call and exits.
- Its log is one line in `~/.config/io.datasette.llm/logs.db` — easy to revisit, easy to re-cost.
- Zero harness overhead beyond the HTTP round trip.

## What the prompt would emit

```json
{
  "class": "pre-agency",
  "cli": "llm",
  "clause_fired": 3,
  "clause_evidence": "summarize the diff for PR #1234 into 5 bullets — single input, single transform, output flows downstream",
  "confidence": "high",
  "note": "no file discovery needed; human produces the diff via gh pr diff"
}
```

## Mismatch shape we're avoiding

If we instead ran this through `claude` or `codex`:

- The agent CLI boots its tool registry (file read, file write, bash, web fetch).
- It runs the model, gets the 5-bullet reply, and exits — but we paid for the harness, the multi-turn context budget, and ~3–5 seconds of startup.
- Tool-call count: zero. The log shows a single model-reply turn. We just spent agent-CLI cost on a pipe-shaped task.

This is the **agent-on-pipe** failure mode from the README. It costs roughly 5–10× the pre-agency equivalent for an identical output.

## Concrete invocation

```bash
gh pr diff 1234 --repo acme/widgets | llm -m gpt-4o-mini -s "$(cat <<'EOF'
Summarize this diff into exactly 5 bullets:
1. Scope (what changed, in 1 sentence)
2. Risk (what could break, in 1 sentence)
3. Test coverage (added / modified / none)
4. Suggested reviewers (1–2 areas of expertise, not names)
5. One open question for the author
EOF
)"
```

One process, one round trip, one line in the log. Task class matches substrate class.
