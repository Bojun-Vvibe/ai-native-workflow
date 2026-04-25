# llm-output-percentage-sum-validator

Validate that groups of percentages in LLM output actually sum to ~100%.

## What it is

A standalone Python script that scans free-form text (typically an LLM
response) for groups of percentages that look like a breakdown — bullet lists,
inline comma-separated runs, and markdown table columns — and flags any group
whose sum drifts beyond a tolerance (default ±1.0 percentage point) from 100%.

## When to use it

LLMs frequently produce "breakdowns" that look authoritative but don't add
up: a 5-bullet list whose percentages sum to 92%, a pie-chart-shaped table
totalling 105%, an "Americas / EMEA / APAC" split that overshoots. Plug this
validator into:

- Post-generation guardrails on analyst / BI / financial summary agents
- Eval harnesses that score factual quality of generated reports
- CI checks on prompt-regression snapshots
- Pre-publish gates for auto-generated stakeholder emails

## How to invoke

```
python3 validate.py < some_llm_output.txt
```

- Reads text from stdin
- Writes a JSON report to stdout
- Exits `0` if all detected groups pass, `2` if any group drifts beyond
  tolerance

Tunable: edit `TOLERANCE` (percentage points) at the top of `validate.py`.

## Detection rules

1. **Bullet lists** — 2+ consecutive bulleted/numbered lines where each
   contains exactly one `NN%` token form a group.
2. **Inline runs** — a line containing 3+ percentages separated by commas or
   semicolons forms a group.
3. **Markdown tables** — any table column whose every data cell is exactly
   one `NN%` token forms a group.

Stdlib only. No third-party dependencies.

## Worked example

Input (`example_input.txt`):

```
User asked: "Break down our Q1 cloud spend by service."

Here is the breakdown of Q1 cloud spend by service:

- Compute: 45%
- Storage: 22%
- Networking: 18%
- Databases: 12%
- Other: 5%

Regional split (single line): Americas: 50%, EMEA: 35%, APAC: 20%

| Service | Share |
| ------- | ----- |
| Web     | 40%   |
| Worker  | 30%   |
| Batch   | 20%   |
| Misc    | 5%    |
```

Run:

```
$ python3 validate.py < example_input.txt; echo "EXIT=$?"
```

Verbatim output:

```
{
  "tolerance_pp": 1.0,
  "groups_checked": 3,
  "groups_failing": 3,
  "findings": [
    {
      "group": "bullet-list@L5",
      "values": [
        45.0,
        22.0,
        18.0,
        12.0,
        5.0
      ],
      "lines": [
        5,
        6,
        7,
        8,
        9
      ],
      "sum": 102.0,
      "drift_from_100": 2.0,
      "ok": false
    },
    {
      "group": "table-col[Share]@L13",
      "values": [
        40.0,
        30.0,
        20.0,
        5.0
      ],
      "lines": [
        15,
        16,
        17,
        18
      ],
      "sum": 95.0,
      "drift_from_100": -5.0,
      "ok": false
    },
    {
      "group": "inline@L11",
      "values": [
        50.0,
        35.0,
        20.0
      ],
      "lines": [
        11,
        11,
        11
      ],
      "sum": 105.0,
      "drift_from_100": 5.0,
      "ok": false
    }
  ]
}
EXIT=2
```

All three group shapes are detected and the bad sums (102, 95, 105) are
flagged with their line numbers, ready to surface back to the generating
agent or block a downstream publish step.
