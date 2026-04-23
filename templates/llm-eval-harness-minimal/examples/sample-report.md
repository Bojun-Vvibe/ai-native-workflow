# Eval report: manifest.example.yaml

Run at: 2026-04-23T10:55:00+00:00
Result: **4/5 passed** (80%)

> This is a representative sample report from the runner with a real
> agent wired in (a coding-summary prompt against a mid-tier model).
> The exact pass/fail pattern will vary; the structural shape is what
> the runner emits.

## Per-case results

| Case | Grader | Verdict | Detail |
|---|---|---|---|
| `case-01-rename-function` | contains_all | **PASS** | all 3 substrings present |
| `case-02-bug-fix` | contains_any | **PASS** | matched: ['UTC', 'timezone'] |
| `case-03-new-feature` | regex | **PASS** | regex matched: '(?i)(adds?|new|introduces?).{0,40}(/health|endpoint|route)' |
| `case-04-noop` | contains_any | **PASS** | matched: ['formatting'] |
| `case-05-structured-summary` | json_schema | **FAIL** | key 'type' not in enum ['feature', 'fix', 'refactor', 'docs', 'chore']: got 'documentation' |

## Failures (full output)

### `case-05-structured-summary`
- Description: When asked for a structured summary, output should be valid JSON with the right keys.
- Detail: key 'type' not in enum ['feature', 'fix', 'refactor', 'docs', 'chore']: got 'documentation'
- Output:
```
{
  "type": "documentation",
  "summary": "Updates the project tagline in README.md to add 'production-ready'.",
  "files": ["README.md"]
}
```

## What this report tells you

- **4/5 passing** is a real signal at this stage of prompt development.
  The cases that pass are catching the obvious shapes the agent should
  handle.
- **The one failure is a controlled vocabulary issue**, not a
  capability issue: the agent produced `"documentation"` where the
  schema accepts only `"docs"`. Two valid responses:
  1. Tighten the prompt to teach the agent the controlled vocabulary
     (e.g., "type must be one of: feature | fix | refactor | docs |
     chore — `docs` not `documentation`").
  2. Loosen the schema to accept synonyms (`enum: ["docs", "documentation", ...]`).
  Pick deliberately. Tightening the prompt is usually right; loosening
  the schema hides the real issue.
- **Run this on every prompt change.** Even at 5 cases, this catches
  regressions cheaply. As the prompt stabilizes, grow the manifest.

## What this report does NOT tell you

- Variance across runs. One pass at temperature > 0 is one data point.
  For a real signal, run the manifest N times and report median.
- Cost. Add a token-counter wrapper around `agent_under_test` if cost
  matters at this stage.
- User experience. Passing graders is necessary, not sufficient.

When the manifest grows past ~30 cases or you need any of the things
above, graduate to a proper eval framework. Before then, this template
is enough.
