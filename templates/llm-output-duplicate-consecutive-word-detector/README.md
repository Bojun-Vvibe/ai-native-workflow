# `llm-output-duplicate-consecutive-word-detector`

Pure-stdlib detector for duplicate consecutive words in an LLM
prose output blob — the classic `the the`, `and and`, `is is`
stutter that emerges from sampling at token boundaries. The
duplicates survive grammar checkers (each word is individually
valid) and survive Markdown linters (it is not a structural
issue), so they leak into commit bodies, PR descriptions, status
updates, runbook prose, and stay there forever.

One finding kind:

- `duplicate_consecutive_word` — the same alphabetic word
  (case-insensitive) appears twice in a row on the same line,
  separated only by whitespace, outside fenced code blocks and
  outside inline code spans.

A small `ALLOWLIST_PAIRS` set carves out genuine English
duplications (`had had`, `that that`, `is is` in copular
constructions, plus a few onomatopoeic pairs `ha ha`, `bye bye`).
The allowlist is deliberately tiny — false negatives are far
cheaper than false positives in a CI gate where alert fatigue
kills adoption.

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, or **release note** before `gh` / `git`
  writes it to a permanent record.
- Pre-flight for an LLM-drafted **status update** or **incident
  postmortem** before paste into a wiki — duplicate words read
  as "the author did not proofread", which is exactly the
  signal you do not want on an incident doc.
- Inside a review loop, the per-finding `(line_number, column,
  word)` triple is small and stable, so a stuck repair loop is
  detectable: same triple two attempts in a row → bail.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` = clean, `1` = at least one finding. JSON on
stdout. Pure-stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array
  into the repair prompt verbatim. The `(word, line_number)`
  pair gives the model a single concrete instruction per stutter.
- `llm-output-mixed-line-ending-detector` — orthogonal: that
  template enforces what the line TERMINATOR looks like, this
  enforces what the line CONTENT looks like.
- `structured-output-repair-loop` — use `detect_duplicates` as
  the per-attempt validator; the `count` field collapses to a
  single integer the loop can compare across attempts.

## Worked example

Input is `example_input.txt`. Run:

```
$ python3 detector.py example_input.txt
```

Verbatim output (exit 1):

```json
{
  "count": 5,
  "findings": [
    {
      "column": 10,
      "context": "When the the model emits a sampl",
      "kind": "duplicate_consecutive_word",
      "line_number": 1,
      "word": "the"
    },
    {
      "column": 23,
      "context": "nd a retry loop will will compound the issue.",
      "kind": "duplicate_consecutive_word",
      "line_number": 3,
      "word": "will"
    },
    {
      "column": 25,
      "context": "here in prose, \"the the\" should be caught.",
      "kind": "duplicate_consecutive_word",
      "line_number": 16,
      "word": "the"
    },
    {
      "column": 61,
      "context": "caught. Same for and and",
      "kind": "duplicate_consecutive_word",
      "line_number": 16,
      "word": "and"
    },
    {
      "column": 61,
      "context": "ine should also fire fire.",
      "kind": "duplicate_consecutive_word",
      "line_number": 17,
      "word": "fire"
    }
  ],
  "ok": false
}
```

Notes:

- Line 2 contains `"is is unstable"` and is **NOT** flagged —
  the allowlist exempts the `is is` pair as a known grammatical
  case ("what it is is unclear"). The cost of the
  exemption is missing the rare LLM stutter on `is`; the
  benefit is zero false positives on copular English.
- The fenced Python block (`the = the`) is **NOT** flagged —
  fenced code is skipped wholesale. A model that emits
  duplicate identifiers in code is leaking a different artifact
  and belongs to a different detector.
- Line 16 fires twice: `the the` mid-line AND `and and` at end
  of line. Multiple findings per line are supported.
- The closing `again.` on line 17 is correctly NOT joined with
  the preceding line — the detector is line-scoped.

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `example_input.txt` — planted-issue input for the worked example
- `README.md` — this file

## Limitations

- The detector is **alphabetic-words-only**: digit runs, mixed
  alphanumeric tokens, and punctuation-separated repeats
  (`5, 5, 5`) are out of scope. Numeric duplication is a
  different artifact (often a real value, not a stutter).
- Capitalised proper-noun pairs (`New York, New York`,
  `Walla Walla`, `Sing Sing`) WILL be flagged. The allowlist
  approach scales poorly to proper nouns; the recommended
  workaround is a project-local denylist suppressed at the
  caller, not a hard-coded global.
- A duplicate split across a soft line break (word at end of
  line N, same word at start of line N+1) is NOT flagged. The
  detector is line-scoped by design — cross-line scanning
  produces too many false positives on legitimate paragraph
  rhythm.
