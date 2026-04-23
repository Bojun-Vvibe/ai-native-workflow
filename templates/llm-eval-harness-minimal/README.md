# Template: Minimal LLM eval harness

A small, opinionated evaluation harness pattern: a YAML manifest of test
cases, a runner that calls a local agent and grades outputs against
expected results, and a markdown report generator. ~150 lines of Python
total. Designed to be the *first* eval harness in a project, before you
graduate to a proper framework.

## Why minimal

The eval-tooling space (promptfoo, ragas, deepeval, weights & biases
prompts, opik, ...) is mature and worth adopting once you have a stable
prompt and a real signal. But before that, those tools are overhead: you're
still figuring out which dimensions to grade on, what your test cases even
look like, and whether your agent is doing the basic thing.

This template is what you start with. ~150 LoC of Python you fully
understand, deterministic where it can be, and easy to delete when you
graduate to a real harness. Keep it as a regression net even after.

## What it does

1. Loads a YAML manifest of test cases. Each case has:
   - `id` — stable identifier
   - `input` — what to send to the agent under test
   - `expected` — the expected output, or a structured assertion
   - `grader` — which built-in grader to use (`exact`, `contains_all`,
     `contains_any`, `regex`, `json_schema`, `llm_judge`)
2. For each case, invokes the agent (a function pointer the user supplies).
3. Grades the output against `expected` using the named grader.
4. Writes a markdown report with per-case pass/fail and an aggregate summary.

## When to use

- You have a prompt or an agent and you want a sanity-check loop before
  every change.
- You want **regression coverage** on the basic capabilities that
  shouldn't break.
- You don't yet have a signal that justifies a heavier eval framework.

## When NOT to use

- You're already running a mature eval harness with dashboards, tracing,
  and trend analysis. Don't downgrade.
- You need cross-run statistical analysis (variance, regression
  detection, A/B comparisons). This template's report is per-run only.
- Your test cases require complex multi-turn agent flows. Add the
  multi-turn support yourself or graduate to a real framework.
- Your test cases need network mocking or fixture sandboxes. Those are
  proper-framework territory.

## Files

- `manifest.example.yaml` — 5 sample test cases for a "summarize a code
  change" task. Realistic enough to demonstrate every grader type.
- `runner.py` — ~150 LoC. Loads manifest, runs cases, writes report.
- `examples/sample-report.md` — what the runner produces against the
  sample manifest.

## Adapt this section

- The `agent_under_test` function in `runner.py` is a stub that returns a
  placeholder. Replace with a call into your actual agent (subprocess,
  HTTP, library import — whatever your agent surface is).
- The graders are deliberately small. Add more in the `GRADERS` dict;
  each grader is a function `(output: str, expected) -> (passed: bool,
  detail: str)`.
- The `llm_judge` grader is stubbed; if you want to use an LLM as a
  judge, wire it to your provider of choice. Use sparingly — LLM-as-judge
  has its own bias problems.

## Running

```
python3 runner.py manifest.example.yaml --report report.md
```

That's the entire interface. No config file, no plugin system, no
dashboards.
