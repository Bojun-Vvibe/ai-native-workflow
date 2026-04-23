# Worked example: behavior spec excerpt for `pew` (one command)

This is one section from the full behavior spec I wrote for
[`pew`][pew] — specifically the `pew render` leaf command — to
show the level of detail Pass 5 should reach. The full spec
covers the entire command tree; this excerpt is one leaf.

Note: `pew` is my own tool, so I had source access — but I wrote
the spec as if I didn't, by probing externally. This made the spec
more useful when other people (and agents) needed to drive it.

[pew]: https://github.com/Bojun-Vvibe/pew-insights

---

### `pew render`

**Synopsis:**
`pew render [--format html|md|json] [--out <path>] [--title <s>] [<input>]`

**Inputs:**
- positional `<input>` (optional): path to a `.pew.json` insights
  file produced by `pew analyze`. If omitted, reads from stdin.
- `--format`: enum `html` | `md` | `json`, default `html`.
- `--out <path>`: file to write to. If omitted, writes to stdout.
- `--title <s>`: human title used in the rendered output's `<h1>`
  (html) or `# ` (md). Default: derived from the input file's
  `metadata.source` field; if absent, the literal string
  `"Insights Report"`.

**Behavior:**
- Validates the input is a JSON object with at least a top-level
  `insights` array. Other fields are passed through to the
  template engine but are not required.
- Renders to the chosen format using a built-in template (no
  external template path supported, despite what `--help`
  suggests in 0.4.x — see Quirk 1).
- Writes to `--out` if given, else stdout.
- Does NOT modify the input file.

**Output (success, `--format html`):**
- stdout (or `--out`): a single self-contained HTML document with
  inline CSS. No external assets, no script tags, no network
  requests at render time.
- stderr: empty.
- Exit code: 0.
- Side effects: if `--out` is given and points to a directory,
  writes `<dir>/insights.html` (does NOT error). See Quirk 2.

**Output (success, `--format json`):**
- stdout schema (the input is normalized and re-emitted with
  computed fields added):
  ```json
  {
    "title": "string",
    "generated_at": "ISO-8601 string",
    "insights": [
      {
        "id": "string",
        "kind": "string",
        "summary": "string",
        "evidence": [{ "path": "string", "line": number }],
        "score": number
      }
    ],
    "stats": { "count": number, "avg_score": number }
  }
  ```
- `generated_at` is non-deterministic; everything else is
  deterministic for a given input.

**Failure modes:**

| trigger | exit code | stderr substring | side effects |
|---|---|---|---|
| input file does not exist | 1 | `cannot read input` | none |
| input is not valid JSON | 2 | `invalid json at line N` | none |
| input lacks `insights` array | 2 | `missing required field 'insights'` | none |
| `--format` value not in enum | 2 | `unknown format` | none |
| `--out` path is unwritable | 1 | `cannot write` | partial file may be left at path |
| stdin is empty (and no positional) | 2 | `no input` | none |
| SIGINT during render | 130 | (none) | partial `--out` file may exist |

**Determinism:** Deterministic for `--format html` and `--format md`.
For `--format json`, only `generated_at` varies.

**Idempotency:** Safe to retry. Output to the same `--out` is an
overwrite, not an append.

**Observed quirks:**

1. **`--template <path>` is documented in `pew render --help` as of
   0.4.2 but is silently ignored.** The built-in template is always
   used. Confirmed by passing a path that does not exist — no error.
   File a bug if you depend on this.
2. **Passing a directory to `--out`** writes `insights.<ext>` inside
   it instead of erroring. This is undocumented and convenient but
   means typos like `--out reports` (intending `reports.html`) will
   silently create `reports/insights.html` if `reports/` exists as a
   directory. Recommend always using a full file path in scripts.
3. **`--title` precedence:** explicit `--title` > input
   `metadata.source` > literal `"Insights Report"`. Empty string
   `--title ""` is treated as "not given", not as "empty title".

---

The full `pew` behavior spec (12 commands, ~700 lines) was written
in about 4 hours of probing once I had the methodology dialed in.
The first command alone took 90 minutes; commands 2–12 averaged
~18 minutes each because most of the time was spent on shared
infrastructure (config file format, global flags, exit-code
conventions) which only had to be probed once.

This is the leverage of the methodology: per-command cost drops
fast as you build up the shared sections.
