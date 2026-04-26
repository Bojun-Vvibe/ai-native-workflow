# llm-output-stale-todo-marker-detector

## Failure mode

An LLM is asked to produce a **final** deliverable — a spec, design doc, PR
description, runbook, or code file. The model returns content that still
contains placeholder / draft markers:

- `TODO`, `FIXME`, `XXX`, `HACK`, `TBD`, `WIP`, `REVISIT`
- angle-bracket placeholders like `<your name here>`, `<placeholder>`,
  `<insert team>`, `<fill in>`
- triple question marks `???` used as a "I don't know" stand-in
- a line consisting solely of `...` (ellipsis used as "fill in the rest")

These are loud signals that the artifact is **not actually final**, but they
slip through human review when the doc is long. Catching them with a
deterministic pre-flight check is cheap.

## How it works

- python3 stdlib only, no deps.
- Word markers are matched **case-sensitive** with `\b` word boundaries, so
  the noun "todo" in normal prose is not flagged — only the all-caps form.
- Angle-bracket placeholder pattern is case-insensitive and matches common
  templates (`<your ...>`, `<insert ...>`, `<placeholder>`, `<name here>`,
  `<fill in>`).
- `???` (3+ consecutive `?`) is flagged anywhere on a line.
- A line that, after stripping, is **only** `...` (3+ dots) is flagged. This
  intentionally does **not** flag `3. ...` in numbered lists or prose
  ellipsis mid-sentence — only lone-line ellipsis used as a "rest goes here"
  marker.

## Exit codes

- `0` — clean, no stale markers.
- `1` — at least one finding; details printed to stdout.

## Invocation

```
python3 detector.py path/to/output.md
# or
cat path/to/output.md | python3 detector.py
```

## Worked example (actual output)

Run on `example/good-input.md`:

```
clean: no stale TODO/placeholder markers found
EXIT=0
```

Run on `example/bad-input.md`:

```
FOUND 6 stale-marker finding(s):
  line 9 [word:TODO]: '- M1: schema freeze — TODO confirm with data team'
  line 10 [word:FIXME]: '- M2: backfill — FIXME numbers below are estimates'
  line 15 [angle-placeholder:<your name here>]: 'Owner: <your name here>'
  line 19 [triple-question-mark]: '- Latency: ???'
  line 20 [word:TBD]: '- Cost: TBD'
  line 31 [word:HACK]: 'HACK around the legacy router until M3.'
EXIT=1
```

Six independent failure-class signals all caught in a single pass, deterministic.
