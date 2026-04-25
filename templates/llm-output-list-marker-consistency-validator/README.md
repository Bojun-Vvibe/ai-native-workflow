# llm-output-list-marker-consistency-validator

Pure stdlib validator for Markdown unordered- and ordered-list
discipline in LLM prose. Catches the silent-corruption class where
the model writes a fluent bulleted list but flips the bullet
character mid-list (`-` → `*` → `+`), skips an ordered number
(`1. 2. 4.`), switches between ordered and unordered halfway through,
or jitter-indents the bullets so the list renders as several
fragments instead of one tree.

These are not parse errors — every Markdown renderer accepts the
input — but they look sloppy in published output and they break
downstream consumers that split on the marker character (e.g. a
log-parser that expects every action item to start with `- `).

## Why a separate template

Existing siblings cover adjacent surfaces:

- `llm-output-markdown-heading-level-skip-detector` — same family
  (Markdown structural discipline) but for `#`/`##`/`###`. Says
  nothing about list markers.
- `llm-output-ordinal-sequence-gap-detector` — generic ordinal
  detector over arbitrary integer sequences. This template
  specializes for the bullet-list surface and adds the
  marker-character checks (`mixed_unordered_marker`, `kind_switch`)
  and the indent check (`indent_jitter`) that are unique to lists.
- `llm-output-quotation-mark-balance-validator` — same paired-token
  discipline pattern, different surface.

This template plugs the gap. Run it before serialising to a
downstream pipeline that consumes bullets line-by-line.

## Findings

Deterministic order: `(kind, line, detail)` — two runs over the same
input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `mixed_unordered_marker` | bullet group starts with `-` then a later line uses `*` or `+` (or any other mismatch) at the same indent column |
| `kind_switch` | bullet group is unordered (`- x`) and a later line at the same indent is ordered (`3. y`) — or vice versa |
| `ordered_numbering_gap` | `1. 2. 4.` — the first gap is reported (later lines are not re-flagged so a single drop doesn't cascade) |
| `indent_jitter` | a bullet line at an indent column the current group didn't open with — usually a typo'd extra space, occasionally a legit nest. The current group is closed and a new group starts at the new column. |

`ok` is `False` iff any finding fires.

## Design choices

- **A "list group" is per-indent-column.** A maximal run of
  consecutive bullet lines at the same leading-space count is one
  group. Blank line, non-bullet line, or indent change ends it.
  This lets the validator treat a properly-nested sublist as its
  own group (no false `mixed_unordered_marker` when the parent uses
  `-` and the child uses `*`, which is a legitimate Markdown
  convention) while still flagging *unintentional* indent jitter
  as `indent_jitter`.
- **Ordered-list gap fires once per group.** After the first gap,
  later mismatches are suppressed — the model dropped one item, the
  rest of the list is still informative, and re-flagging every
  subsequent line would drown the real signal.
- **One forward scan, no regex.** Single pass, line-by-line.
- **Eager refusal on bad input.** `prose` not a `str` raises
  `ListMarkerValidationError` immediately. Empty prose is *valid*
  (zero groups, zero findings).
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json`. No `re`.

## Composition

- `llm-output-markdown-heading-level-skip-detector` — heading
  discipline; same family. Run both as a "Markdown structural
  hygiene" gate.
- `llm-output-fence-extractor` — strip fenced code blocks first if
  the prose contains code that uses `* ` or `- ` for emphasis or
  shell prompts; feed only the narrative spans into this validator.
- `agent-decision-log-format` — one log line per finding sharing
  `line` so a reviewer can jump to the offending row.
- `structured-error-taxonomy` — `mixed_unordered_marker` /
  `kind_switch` / `indent_jitter` → prompt-template instrumentation
  bug (the model is being asked to emit a list and is being sloppy);
  `ordered_numbering_gap` → almost always a dropped sentence in the
  middle of an enumerated answer.

## Worked example

Run `python3 example.py` from this directory. Seven cases — two
clean (a single dash list, plus two separate clean lists) and five
each demonstrating a distinct finding family. The output below is
captured verbatim from a real run.

```
# llm-output-list-marker-consistency-validator — worked example

## case 01_clean_dash
prose:
  | Steps:
  | - one
  | - two
  | - three
{
  "findings": [],
  "groups": 1,
  "ok": true
}

## case 02_mixed_unordered_dash_then_star
prose:
  | Pros:
  | - fast
  | * cheap
  | - simple
{
  "findings": [
    {
      "detail": "marker '*' in a list that started with '-'",
      "kind": "mixed_unordered_marker",
      "line": 3
    }
  ],
  "groups": 1,
  "ok": false
}

## case 03_mixed_dash_plus_star
prose:
  | Notes:
  | - alpha
  | + beta
  | * gamma
{
  "findings": [
    {
      "detail": "marker '+' in a list that started with '-'",
      "kind": "mixed_unordered_marker",
      "line": 3
    },
    {
      "detail": "marker '*' in a list that started with '-'",
      "kind": "mixed_unordered_marker",
      "line": 4
    }
  ],
  "groups": 1,
  "ok": false
}

## case 04_ordered_numbering_gap
prose:
  | Recipe:
  | 1. boil water
  | 2. add tea
  | 4. steep
  | 5. serve
{
  "findings": [
    {
      "detail": "ordered list expected 3. but got 4.",
      "kind": "ordered_numbering_gap",
      "line": 4
    }
  ],
  "groups": 1,
  "ok": false
}

## case 05_kind_switch_mid_list
prose:
  | Plan:
  | - draft
  | - review
  | 3. ship
{
  "findings": [
    {
      "detail": "switched from unordered to ordered mid-list (marker '3')",
      "kind": "kind_switch",
      "line": 4
    }
  ],
  "groups": 1,
  "ok": false
}

## case 06_indent_jitter
prose:
  | Outline:
  | - top
  |   - nested
  |  - oddly indented
{
  "findings": [
    {
      "detail": "bullet at column 2 after group started at column 0",
      "kind": "indent_jitter",
      "line": 3
    },
    {
      "detail": "bullet at column 1 after group started at column 2",
      "kind": "indent_jitter",
      "line": 4
    }
  ],
  "groups": 3,
  "ok": false
}

## case 07_two_separate_clean_lists
prose:
  | First list:
  | - a
  | - b
  | 
  | Second list:
  | * x
  | * y
{
  "findings": [],
  "groups": 2,
  "ok": true
}
```

The output above is byte-identical between runs — `_CASES` is a fixed
list, the validator is a pure function, and findings are sorted by
`(kind, line, detail)` before serialisation.

## Files

- `example.py` — the validator + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.
