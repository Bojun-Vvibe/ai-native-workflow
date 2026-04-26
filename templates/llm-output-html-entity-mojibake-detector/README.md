# llm-output-html-entity-mojibake-detector

## Problem

Two related encoding bugs sneak into LLM output and survive review
because they look almost-correct at a glance:

1. **Stray HTML entities** — the model emits `&amp;`, `&#39;`, `&lt;`,
   `&nbsp;` and so on in finished prose where the user obviously
   wanted a literal `&`, `'`, `<`, or non-breaking space. This often
   happens when the model has been trained on HTML-escaped corpora
   and emits escape sequences in plain-text contexts.

2. **Mojibake** — UTF-8 bytes were decoded as Latin-1/cp1252 and then
   re-encoded as UTF-8, producing the classic `â€™` (curly apostrophe),
   `â€œ` / `â€\x9d` (curly quotes), `Ã©` (é), `Â ` (U+00A0) sequences.
   Once these land in a doc, copy-pasting them downstream just
   propagates the corruption.

Both are silent: they render as visible text, no exception is thrown,
and they typically only get caught when a human notices something
ugly in a published artifact.

## Use case

- Run as a post-generation lint over LLM output before it is shown to
  a user, written to disk, or PR'd into a docs repo.
- Run over an entire docs tree as a CI check.
- Pair with a fixer that round-trips the bytes through
  `latin-1 → utf-8` and `html.unescape` to auto-repair, only after a
  human reviews the detector report.

## What it detects

- Named entities that should have been decoded:
  `&amp; &lt; &gt; &quot; &apos; &nbsp; &copy; &reg; &trade; &hellip;
  &mdash; &ndash; &lsquo; &rsquo; &ldquo; &rdquo; &bull; &deg;
  &plusmn; &times; &divide; &laquo; &raquo; &sect; &para;`
- Any numeric entity: `&#NNN;` or `&#xHH;`.
- Mojibake byte fragments for the most common offenders (curly
  quotes, em/en dashes, ellipsis, no-break space, é/è/â/í/ó/ú/ñ,
  UTF-8 BOM rendered as mojibake).

## How to run

```
python3 detector.py <path-to-text-file>
```

Exit code `0` means clean, `1` means at least one issue was found.

## Worked example

Input lives at `worked-example/sample.md`:

```
The summary above includes the customer&#39;s pricing &amp; terms. The
launch is scheduled for the second quarter â€" details still TBD.

Notes from the field team:
- "Itâ€™s working" reports came in from three regions.
- Latency dropped to &lt;200ms after the rollout.
- The cafÃ© demo (Ã©clair tasting) ran clean.
- Tariff applied: 5&nbsp;EUR per unit.

Followâ€"up actions: confirm with the partner&#x27;s legal team.
```

Run:

```
$ python3 detector.py worked-example/sample.md
```

Actual output:

```json
{
  "path": "worked-example/sample.md",
  "issue_count": 8,
  "issues": [
    {
      "kind": "stray_named_entity",
      "line": 1,
      "col": 55,
      "match": "&amp;",
      "hint": "Decode this HTML entity to its literal character."
    },
    {
      "kind": "stray_numeric_entity",
      "line": 1,
      "col": 40,
      "match": "&#39;",
      "hint": "Decode this numeric HTML entity to its literal character."
    },
    {
      "kind": "mojibake_sequence",
      "line": 5,
      "col": 6,
      "match": "â€™",
      "hint": "U+2019 right single quote misencoded"
    },
    {
      "kind": "stray_named_entity",
      "line": 6,
      "col": 22,
      "match": "&lt;",
      "hint": "Decode this HTML entity to its literal character."
    },
    {
      "kind": "mojibake_sequence",
      "line": 7,
      "col": 10,
      "match": "Ã©",
      "hint": "U+00E9 e-acute misencoded"
    },
    {
      "kind": "mojibake_sequence",
      "line": 7,
      "col": 19,
      "match": "Ã©",
      "hint": "U+00E9 e-acute misencoded"
    },
    {
      "kind": "stray_named_entity",
      "line": 8,
      "col": 20,
      "match": "&nbsp;",
      "hint": "Decode this HTML entity to its literal character."
    },
    {
      "kind": "stray_numeric_entity",
      "line": 10,
      "col": 46,
      "match": "&#x27;",
      "hint": "Decode this numeric HTML entity to its literal character."
    }
  ]
}
```

Exit code: `1`.

## Limitations

- The mojibake catalog is the common-offender shortlist, not exhaustive.
  Add more `(needle, hint)` pairs to `MOJIBAKE_PATTERNS` for languages
  you care about.
- The named-entity list deliberately excludes entities that frequently
  appear inside legitimate raw HTML embedded in markdown. If you scan
  raw HTML, expect false positives and pre-strip code/HTML blocks.
- Only stdlib used (`re`, `argparse`, `json`).
