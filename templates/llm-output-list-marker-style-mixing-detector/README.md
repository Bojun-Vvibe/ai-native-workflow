# `llm-output-list-marker-style-mixing-detector`

Pure-stdlib detector for **mixed unordered-list marker styles** in
LLM output. Markdown allows three unordered-list markers: `-`, `*`,
and `+`. Any single list should pick one and stick with it. LLMs
commonly drift mid-list — emitting `-` for the first three items,
then `*` for the fourth, often after a paragraph break the model
"forgot" was inside a list. The result renders fine on most
renderers but reads as two adjacent lists, breaks list-counting
downstream tools, and looks visibly sloppy in any committed doc.

This detector groups consecutive same-indent unordered-list items
into "list runs" and flags any run that uses more than one distinct
marker.

One finding kind:

- `mixed_unordered_list_markers` — one finding per drifted run.
  Reports the line range, the per-marker tally, the indent level,
  and the line numbers where the marker switched.

Fenced code blocks (` ``` ` or `~~~`) are skipped wholesale. Ordered
list items (`1.`, `2.`) are out of scope here — see
`llm-output-markdown-ordered-list-numbering-monotonicity-validator`.

## When to use

- Pre-publish gate on any LLM-generated **runbook**, **release
  note**, or **PR description** before it lands in a permanent
  record. Mixed bullet markers in a single list is the cheapest
  visible "an LLM wrote this and nobody read it" tell.
- Inside a **review-loop** validator: the
  `(start_line, marker_tally)` pair is small and stable, so a
  stuck repair loop is detectable across attempts (same tally
  twice → bail to a human).
- As a **style-postcondition** on prompt templates that ask the
  model for "a list of N items": if the model drifts marker style,
  it usually also drifted in some semantic dimension (item shape,
  parallelism, voice). Marker drift is a cheap proxy signal.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON on stdout.
Pure-stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array into
  a repair prompt verbatim. The `marker_tally` field tells the
  model which marker is the majority; the canonical repair is
  "rewrite all bullets in this run with the majority marker".
- `llm-output-empty-list-bullet-detector` — orthogonal: that
  template enforces *bullet content*, this one enforces *bullet
  style consistency*. Together they catch most LLM list bugs.
- `structured-output-repair-loop` — use `detect_mixed_markers` as
  the per-attempt validator. The `count` field collapses to a
  single integer per attempt for trivial loop-stuckness detection.

## Worked example

Input is `example_input.txt` — clean lists (dash-only, star-only),
nested clean sublists, deliberately drifted runs, fenced-block
negatives, and `*emphasis*` / `1.5` decimal negatives.

```
$ python3 detector.py example_input.txt
```

Verbatim output (exit 1):

```json
{
  "count": 3,
  "findings": [
    {
      "end_line": 13,
      "indent": 0,
      "kind": "mixed_unordered_list_markers",
      "marker_tally": {
        "*": 2,
        "-": 2
      },
      "start_line": 10,
      "switch_lines": [
        12
      ]
    },
    {
      "end_line": 38,
      "indent": 2,
      "kind": "mixed_unordered_list_markers",
      "marker_tally": {
        "+": 1,
        "-": 1
      },
      "start_line": 37,
      "switch_lines": [
        38
      ]
    },
    {
      "end_line": 60,
      "indent": 0,
      "kind": "mixed_unordered_list_markers",
      "marker_tally": {
        "*": 1,
        "+": 1,
        "-": 1
      },
      "start_line": 58,
      "switch_lines": [
        59,
        60
      ]
    }
  ],
  "ok": false
}
```

Notes:

- The pure-dash list at the top (lines 3-5) and the pure-star
  list (lines 19-21) are correctly NOT flagged.
- The drifted run at lines 10-13 (`- - * *`) is flagged with
  `switch_lines: [12]` — a single switch from `-` to `*` between
  items 2 and 3. A repair prompt can quote that exact line.
- The nested clean case (lines 28-32) is correctly NOT flagged:
  the outer run is pure-dash, each inner run is pure-star, and
  the runs are tracked separately by indent level.
- The nested *drifted* case at indent 2 (lines 37-38) IS flagged
  with `indent: 2` — nested-list drift is just as ugly as
  top-level drift and equally easy to miss in review.
- The fenced block (lines 50-54) contains `- foo / * bar / + baz`
  and is correctly NOT flagged — fence content is pretend-code,
  not real lists.
- `*emphasis*` and `1.5x speed` are correctly NOT flagged: the
  bullet regex requires a space or tab after the marker.

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `example_input.txt` — planted-issue input (clean, drifted,
  nested, fenced, decimal/emphasis negatives)
- `example_output.txt` — captured output of the worked example
- `README.md` — this file

## Limitations

- The detector treats indent purely by leading-space count. A list
  that mixes 2-space and 4-space indents for the same logical
  level will be split into separate runs. That mostly does the
  right thing — mixed indent is itself a smell — but the
  `start_line`/`end_line` ranges may be narrower than a human
  would draw them.
- Tab-indented bullets are not flagged as bullets at all
  (the regex requires `space*`). If your house style uses tabs
  for bullet indentation, expand `BULLET_RE` accordingly.
- A single-item run can never be flagged (one marker = no drift),
  even if it's surrounded by lists with a different marker. That
  is the correct call: a one-item "list" that happens to use a
  different marker than the previous list is just a separate
  list, not a drift.
- Two consecutive blank lines terminate a run. A single blank
  line does not — Markdown's "loose list" rule means a single
  blank line between bullets keeps the list open.
