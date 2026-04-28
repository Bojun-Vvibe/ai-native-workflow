# llm-output-yaml-indentation-mix-detector

Pure-stdlib detector that scans **only the YAML fenced code blocks**
inside markdown emitted by an LLM and flags indentation hazards that
will silently re-shape the parsed tree (or hard-fail one parser while
another tolerates it). The model never sees which YAML parser the
downstream consumer uses; this detector catches the smell before the
doc is fanned out.

## Why a separate template

YAML hazards are not covered by the existing markdown / JSON detectors:

- `llm-output-markdown-yaml-frontmatter-validator` validates the
  `---`-delimited frontmatter block at the top of a markdown doc, not
  the body of a `yaml` fenced code block.
- `llm-output-fenced-code-indent-tab-space-mix-detector` flags tab/space
  mix in **any** code fence; this detector is YAML-aware: it flags
  tabs in `yaml` fences only and additionally flags **mixed indent
  step** (e.g. 2-space at one level, 4-space at the next) which is
  invisible to a generic tab/space mixer but is a real YAML hazard.
- `llm-output-mixed-line-ending-detector` looks at the whole file;
  this detector flags CR bytes **inside the yaml block specifically**,
  because some strict YAML parsers reject CRLF inside the document
  even when the surrounding markdown is happy.

## What it catches

| kind | what it catches |
|---|---|
| `tab_in_indent` | a TAB character appears in the leading whitespace of a non-blank line inside a yaml fence (PyYAML rejects this outright) |
| `mixed_indent_step` | sibling nesting levels in the same yaml block use different indent widths (e.g. 2-space at one level, 4-space at the next) |
| `indent_step_zero` | a child line is indented the same as its parent — defensive guard for malformed YAML |
| `cr_line_ending` | a CR byte appears at end-of-line inside the yaml block (CRLF or bare-CR) |

## Why parser disagreement matters

The same YAML emitted in a fenced code block is consumed by different
tools depending on the pipeline:

- PyYAML / ruamel.yaml — reject TAB in indent with a hard error
- `yq` (Go) — tolerates TAB in some positions, re-shapes silently
- `js-yaml` — tolerates mixed indent step; re-parses keys at whichever
  indent width was first seen at that level
- `yaml-cpp` — its own quirks

If a CI lint job uses PyYAML and a runtime ingest uses `js-yaml`, a
"good enough" YAML block can lint-fail in CI while running fine in
prod, or vice versa. A detector at emit-time catches this before the
two consumers ever see the doc.

## Design choices

- **Code-fence-aware.** Only scans inside ``` ```yaml ``` / ``` ```yml ```
  fences (case-insensitive, matches `yaml`, `yml`, `YAML`). Everything
  outside is ignored — we are not a YAML parser, we sniff hazards in
  YAML embedded in LLM markdown output.
- **Document-separator-aware.** `---` and `...` reset the indent stack
  inside a yaml block.
- **Block-scalar-aware.** After a key ending in `|`, `>`, `|-`, `>-`,
  `|+`, `>+`, the indented body is treated as opaque (its indent is
  its content). Tabs in that body are still flagged.
- **Comment-aware.** Lines starting with `#` are skipped for indent
  reasoning but still flagged for tab leakage.
- **Deterministic order.** Findings sorted by `(line_no, col_no, kind)`.
- **Pure function.** `detect(src) -> YamlIndentReport`. No I/O, no
  clocks, no transport.
- **Stdlib only.** `dataclasses`, `json` (only for serialising the
  report), `sys`. No `re`, no `yaml`, no third-party parser.

## Composition

- `llm-output-fence-extractor` — run upstream if you only want to
  inspect fenced blocks. This detector runs the extraction internally.
- `llm-output-fenced-code-language-tag-missing-detector` — run first;
  YAML blocks with no language tag are invisible to this detector by
  design.
- `llm-output-mixed-line-ending-detector` — orthogonal; that one
  flags whole-file mix, this one flags CR bytes only inside yaml fences.

## Worked example

`bad/example.md` contains a yaml block with three planted hazards:
2→1-space step at `timeout_s`, a TAB in the indent of one endpoint
list item, and a 1→3-space step on the next endpoint.

`good/example.md` is the same shape with consistent 2-space indent
and no tabs.

### Running the detector

```
$ python3 detector.py bad/example.md good/example.md
=== bad/example.md ===
{
  "findings": [
    {
      "col_no": 3,
      "detail": "indent step changed from 2 to 1 spaces between sibling nesting levels in the same yaml block",
      "kind": "mixed_indent_step",
      "line_no": 9
    },
    {
      "col_no": 1,
      "detail": "TAB character in leading whitespace; PyYAML and strict parsers reject this outright",
      "kind": "tab_in_indent",
      "line_no": 12
    },
    {
      "col_no": 2,
      "detail": "indent step changed from 1 to 3 spaces between sibling nesting levels in the same yaml block",
      "kind": "mixed_indent_step",
      "line_no": 13
    }
  ],
  "ok": false,
  "yaml_blocks_checked": 1,
  "yaml_lines_checked": 8
}
=== good/example.md ===
{
  "findings": [],
  "ok": true,
  "yaml_blocks_checked": 1,
  "yaml_lines_checked": 8
}
exit=1
```

The bad doc trips three findings on the planted hazards; the good
doc passes silently. The exit code is 1 if any input has findings,
0 otherwise — usable in pre-commit / CI without further wiring.

## Counts

- bad/: 1 markdown file, 1 yaml block, 3 planted hazards, 3 findings
- good/: 1 markdown file, 1 yaml block, 0 hazards, 0 findings

## Non-goals

- This is **not** a YAML parser. It does not validate that the YAML
  document is well-formed; a doc with mismatched braces in a flow
  collection can still pass this detector.
- It does not opine on indent width (2-space vs 4-space) — only on
  **mixing** widths within a single block.
- It does not inspect non-yaml fences. Use the existing tab/space-mix
  detector for those.
