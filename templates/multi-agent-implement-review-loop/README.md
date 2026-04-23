# Template: Multi-agent implement-review loop with arbiter escalation

A pattern for parallelized work-package execution where each WP runs through
an `implement → review → (rejected? loop) → arbiter → human` ladder, instead
of a single agent doing both jobs.

## The pattern

```
                    ┌────────────────────────┐
                    │  WP queue (DAG order)  │
                    └──────────┬─────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       ┌────────────┐   ┌────────────┐   ┌────────────┐
       │ implementer│   │ implementer│   │ implementer│   (N in parallel)
       │  WP-A      │   │  WP-B      │   │  WP-C      │
       └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
             │                │                │
             ▼                ▼                ▼
       ┌────────────┐   ┌────────────┐   ┌────────────┐
       │  reviewer  │   │  reviewer  │   │  reviewer  │
       └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
             │                │                │
       approve│reject   approve│reject   approve│reject
             │                │                │
             ▼          (loop up to K rounds)  ▼
       ┌────────────┐                    ┌────────────┐
       │   merge    │                    │  arbiter   │  (only if K rounds exhausted)
       └────────────┘                    └─────┬──────┘
                                               │
                                       decide │ defer
                                               ▼
                                         ┌────────────┐
                                         │   human    │
                                         └────────────┘
```

- **Implementer**: writes the code change for one WP. Operates under a
  conservative profile (see `templates/agent-profile-conservative-implementer/`).
- **Reviewer**: a *different* agent (different prompt, ideally different
  model) that reads the implementer's diff and either approves or rejects
  with structured feedback.
- **Loop**: rejected WPs re-enter implement with the reviewer's feedback,
  up to K rounds (default: 3).
- **Arbiter**: a third agent invoked only when the implementer and reviewer
  cannot converge in K rounds. The arbiter reads both sides' last messages
  and either rules in favor of one, proposes a synthesis, or defers to a
  human.
- **Human**: gate of last resort. Sees the full transcript and the
  arbiter's recommendation.

## When to use

- Mission has **many independent WPs** (10+) that can run in parallel.
- WPs have **clear acceptance criteria** the reviewer can check
  mechanically.
- You're running on **multiple model providers / contexts** so the
  reviewer is genuinely independent (a same-model self-review is much
  weaker).
- **Quality matters more than speed**. The loop adds latency.

## When NOT to use

- **Single-WP missions** — overhead doesn't pay off.
- **Exploratory / research work** — there is no objective "approved"
  state, so the reviewer can't add signal.
- **Tight token budget** — every WP is paid for at least twice (implement
  + review), and rejection cycles multiply that.
- **Workflows where the same model serves implementer and reviewer with
  the same prompt context** — that's just self-review with extra steps;
  the second pass agrees with the first by construction.

## Files

- `mission.example.yaml` — wiring for the four roles and the loop.
- `prompts/implementer.md` — the implementer's contract.
- `prompts/reviewer.md` — the reviewer's contract.
- `prompts/arbiter.md` — the arbiter's contract.
- `examples/sample-loop.md` — a representative end-to-end transcript.

## Adapt this section

- `max_parallel` in `mission.example.yaml` — how many WPs run concurrently.
  Bound by model provider rate limits, not by ambition.
- `max_rounds` (default 3) — how many implement-review cycles before
  arbiter escalation. Lower for cheap tasks; higher for high-stakes ones.
- Reviewer's `mechanical_checks` list — these are the bright-line tests.
  Anything checkable by a regex or a script should be here, not in prose.
- Arbiter's `defer_to_human_when` list — when in doubt, the arbiter should
  defer, not decide. Tune this conservatively at first.

## Cost shape

Per WP, expect:

- Implementer: 1 input + 1 output per round.
- Reviewer: 1 input + 1 output per round.
- Arbiter: invoked in <10% of WPs in a healthy mission. If you see it
  fire often, either the spec is ambiguous or one of the prompts is
  wrong.
- Total: roughly 2× a single-agent baseline for happy-path WPs, 4–6× for
  WPs that need a full loop.

If your bill is more than 3× single-agent on a typical mission, the
reviewer is rejecting too aggressively. Tighten its criteria.
