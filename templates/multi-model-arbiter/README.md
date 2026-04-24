# Template: Multi-model arbiter

Route the **same prompt** to N candidate models, score each response
with a **task-specific criterion**, and return the winner plus a full
trace of who-said-what and why.

Pure stdlib. The model client is an injected callable, so this module
never knows or cares which provider you use.

## Why this exists

When you don't know which model is best for a given task, the
honest answer is to ask all of them, score the answers, and keep the
best one. This template makes that pattern boring and reusable
instead of one-off and forgotten:

- **Latency-vs-quality tradeoffs** become measurable, not theoretical.
- **Model regressions** show up as score drops on a known-good prompt
  set without you having to read every diff.
- **New models** are evaluated by adding one string to a list, not by
  rewriting your call site.

## When to use

- You have a **scorable** task — JSON extraction, code that compiles,
  classification with a known label, summary with a checkable
  property. Anything where "is this answer good?" can be reduced to a
  function returning a number.
- You're picking between providers and want apples-to-apples evidence
  on **your** prompts, not someone's leaderboard.
- You can afford N× the cost of a single call. Arbitration is fan-out;
  budget accordingly.

## When NOT to use

- The task is unscorable (open-ended creative writing, opinion). A
  fan-out without a criterion is just an expensive jumble.
- Latency matters more than quality. Arbitration is bounded by the
  slowest candidate, not the fastest.
- You already know one model dominates on this task. Pay for one
  call, not three.

## Anti-patterns

- **"LLM-as-judge" without a baseline.** A second model scoring the
  first is fine, but pin a deterministic property too (parses, has
  required keys, length within band). Pure judge-LLM scoring drifts
  silently when the judge model changes.
- **Random tie-breaking.** Use the input order. Reproducibility >
  cleverness.
- **Discarding the losers.** Always log every candidate's response
  and score. The losers are training data for your prompt and your
  criterion.
- **Treating an exception as `score=0`.** Exceptions should be
  `-inf`, not 0, otherwise a model that crashes consistently will
  beat a model that returns merely-bad output. The example uses
  `float('-inf')` for errors.
- **Tuning the criterion to the answers.** Write the criterion before
  you see any model output, or you've built a lookup table, not a
  scorer.

## Files

- `src/arbiter.py` — the orchestrator. Single public function
  `arbitrate(prompt, models, model_call, criterion, *, label=None)`
  returning an `ArbitrationResult` dataclass with `to_json()`.
- `examples/run_example.py` — JSON-extraction task with three fake
  models exhibiting three failure modes (clean, fenced, prose). Fully
  reproducible without any provider keys; swap `fake_call` for your
  real client.

## Verified output

Running `python3 examples/run_example.py`:

```
{
  "candidates": [
    {
      "elapsed_ms": 0,
      "error": null,
      "evidence": {
        "had_fence": false,
        "keys": ["city", "country", "temperature_c"],
        "temperature_plausible": true
      },
      "model": "model-a",
      "response": "{\"city\": \"Lisbon\", \"country\": \"Portugal\", \"temperature_c\": 14}",
      "score": 1.0
    },
    {
      "elapsed_ms": 0,
      "error": null,
      "evidence": {
        "had_fence": true,
        "keys": ["city", "country", "temperature_c"],
        "temperature_plausible": true
      },
      "model": "model-b",
      "response": "```json\n{\"city\": \"Lisbon\", ...}\n```",
      "score": 0.95
    },
    {
      "elapsed_ms": 0,
      "error": null,
      "evidence": {
        "had_fence": false,
        "parse_error": "Expecting value: line 1 column 1 (char 0)"
      },
      "model": "model-c",
      "response": "The city was Lisbon and it was about fourteen degrees.",
      "score": -1.0
    }
  ],
  "label": "json-extraction-demo",
  "winner": "model-a",
  "winner_score": 1.0
}

WINNER: model-a  score=1.000
```

Note that `model-b` (the markdown-fenced response) lost to `model-a`
by exactly the 0.05 fence penalty — a deliberate tie-break that
prefers the cleaner emitter. This is the kind of property the
criterion should encode explicitly so you can reason about wins
later.

## Composing with other templates

- Combine with [`prompt-regression-snapshot`](../prompt-regression-snapshot/)
  to track winner-stability across model versions over time.
- Combine with [`token-budget-tracker`](../token-budget-tracker/) so
  the N× fan-out cost is visible in your weekly report.
- Combine with [`cost-budget-soft-fence`](../cost-budget-soft-fence/)
  to cap arbitration to single-model fallback once a soft cost ceiling
  is crossed.
