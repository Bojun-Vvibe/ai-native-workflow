# llm-output-language-mismatch-detector

Pure, stdlib-only detector that decides whether an LLM response is plausibly
in the *expected* natural-language script. Returns one of four verdicts so the
orchestrator can route silently-drifting outputs to a re-prompt or fallback
path *before* they reach a downstream consumer (TTS, translation memory,
regex extractor) that doesn't validate language.

## Why this template exists

A user prompts in English; the model answers in Chinese (or vice versa)
because earlier turns drifted, retrieved context was in a different
language, or the system prompt got dropped under cache pressure. **Silent
language drift is invisible to a JSON schema validator**: the *shape* is
correct, the *language* is wrong. By the time a human notices, the bad
output is already in the audit log, the user-visible UI, the dataset.

This template is the cheap pre-flight gate that catches it at the orchestrator
boundary. It is intentionally crude (Unicode-block heuristics, not full
language ID) because:

- The question agents need answered is "is the model answering in roughly
  the right script?" — not "is this Brazilian or European Portuguese".
- A heavy ML language-id dependency is a poor trade for a guard that runs on
  every turn.
- Crude is auditable: the verdict explains itself in counts.

## Verdicts

The detector returns one of four verdicts so each maps to a different
recovery path:

| Verdict        | Meaning                                                                        | Typical orchestrator action                              |
| -------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------- |
| `match`        | expected family is ≥ `min_ratio` of classifiable chars                         | accept                                                   |
| `mixed`        | expected family present but below `min_ratio`                                  | re-prompt with explicit language pin; usually a one-shot fix |
| `mismatch`     | a *different* script family dominates                                          | re-prompt or fall back to a more obedient model          |
| `insufficient` | fewer than `min_chars` classifiable characters (e.g. JSON-only, code-only)     | caller decides — "no language signal" is not "wrong"     |

The `insufficient` verdict matters: a structured JSON response or a
code-only completion has no language signal at all, and forcing a verdict
in that case would generate false `mismatch` events on every successful
schema-strict call.

## Hard rules

- **Pure stdlib** (`unicodedata`, `dataclasses`).
- **No I/O, no clocks, no global mutable state** — the detector is a
  function-shaped value object.
- **Whitespace, ASCII punctuation, digits, symbols, and emoji are ignored**
  in the ratio denominator. They carry no language signal and including them
  would silently inflate `match` for a JSON-heavy CJK response.
- **Unknown `expected` family raises `LanguageConfigError` at call time** —
  silent default-to-latin would defeat the gate.
- **Verdict reasons are populated for every result**, including `match`, so
  a downstream audit log can answer "why did this pass?" without re-running
  the detector.

## Files

| File                      | What it is                                              |
| ------------------------- | ------------------------------------------------------- |
| `detector.py`             | The detector — one public function `detect(...)`        |
| `worked_example/run.py`   | Five scenarios + one config-error case + invariants     |

## Composes with

- `agent-output-validation` / `llm-output-jsonschema-repair` — schema gate
  validates *shape*; this gate validates *language*. Run schema first
  (cheaper), language second (only on text-bearing outputs).
- `structured-output-repair-loop` — a `mixed` or `mismatch` verdict is the
  trigger to re-prompt with `language=...` pinned, capped by a small retry budget.
- `prompt-regression-snapshot` — a sudden spike in `mismatch` rate against
  yesterday's snapshot is a strong "model swap regressed" signal.
- `agent-decision-log-format` — one log line per non-`match` verdict
  (`{verdict, expected, dominant, ratio, classified}`) is enough to
  forensically reproduce the call.
- `llm-output-trust-tiers` — feed `verdict != "match"` into the tier router
  as an additional demotion signal alongside `repair_count` and
  `canary_passed`.

## Worked example output (verbatim)

```
1. clean english reply
   verdict=match expected=latin dominant=latin ratio=1.00 classified=49
   reason: 49/49 = 1.00 >= 0.7

2. silent drift to chinese
   verdict=mismatch expected=latin dominant=cjk ratio=0.00 classified=25
   reason: zero latin chars; dominant=cjk=25

3. code-switched mid-answer (heavy mix)
   verdict=mixed expected=latin dominant=cjk ratio=0.34 classified=32
   reason: expected=11/32=0.34 below 0.7; dominant=cjk=21

4. pure-symbol output (no language signal)
   verdict=insufficient expected=latin dominant=None ratio=0.00 classified=3
   reason: only 3 classifiable chars (need >= 20)

5. expected cjk, got cjk
   verdict=match expected=cjk dominant=cjk ratio=1.00 classified=31
   reason: 31/31 = 1.00 >= 0.7

6. unknown family raises LanguageConfigError:
   raised: unknown expected family: 'klingon' (allowed: ('latin', 'cjk', 'cyrillic', 'arabic', 'devanagari', 'hebrew', 'greek'))

invariants ok: pure-latin match=1.0, pure-cjk mismatch->cjk dominant
```

Reproduce: `python3 worked_example/run.py` from this directory.
