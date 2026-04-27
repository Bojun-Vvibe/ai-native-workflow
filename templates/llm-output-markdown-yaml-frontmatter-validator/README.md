# llm-output-markdown-yaml-frontmatter-validator

Pure stdlib detector that scans a markdown document produced by an
LLM for malformed YAML frontmatter blocks. The failure mode it
catches: the model emits a doc with a frontmatter block that *looks*
right but breaks downstream — Hugo / Jekyll / Eleventy / MkDocs
silently drop the doc, the static-site index loses it, the
RAG indexer skips its metadata, and a publishing pipeline reports
"0 docs ingested" with no error trail.

The validator is deliberately stricter than PyYAML, because PyYAML
accepts inputs that real static-site generators and our own
metadata pipelines reject. The job here is to flag the smell
*before* it hits the parser that will quietly accept it and produce
the wrong document.

## Why a separate template

Existing siblings cover adjacent concerns:

- `llm-output-fence-extractor`,
  `llm-output-markdown-fence-orphan-closing-detector` — fenced
  *code* blocks. Frontmatter uses `---` / `...` delimiters which
  are not fences and parse with completely different rules.
- `llm-output-markdown-heading-level-skip-detector` — heading tree
  structure. Frontmatter is metadata; this validator never inspects
  the body.
- `llm-output-citation-bracket-balance-validator`,
  `llm-output-quotation-mark-balance-validator` — character-balance.
  Orthogonal — frontmatter validity is structural and key-aware.
- `prompt-template-versioner` — versions the *prompt*. This
  validates the *output*.

## Findings

Deterministic order: `(kind, line_no, detail)` — two runs over the
same input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `missing_open` | doc starts with `...` (close marker) without a prior `---` opener |
| `missing_close` | doc opens with `---` on line 1 but no closing `---` / `...` line is found before EOF |
| `not_at_top` | a `---`...`---` block appears later in the doc and looks like frontmatter; static site generators only honour frontmatter on line 1 |
| `empty_block` | the frontmatter delimiters are present but the body between them is empty or whitespace-only; some renderers treat this as a horizontal rule |
| `tab_indent` | a body line uses a tab for indentation; YAML 1.2 forbids tabs as indent and many parsers reject the file |
| `duplicate_key` | a top-level key appears twice; YAML allows it but downstream consumers silently use only one and the choice differs across tools |
| `unquoted_special` | a top-level scalar value starts with a YAML special character (`@`, `` ` ``, `%`, `&`, `*`, `!`, `|`, `>`, `?`) and is not quoted |
| `missing_colon_space` | a body line uses `key:value` with no space after the colon; YAML requires `key: value` for plain scalars |
| `bom_in_block` | a UTF-8 BOM appears inside the frontmatter body — almost always means the doc was concatenated from two sources |

`ok` is `False` iff any finding fires.

## Design choices

- **Frontmatter must start on line 1.** If line 1 is not `---`, the
  validator does not look for an opener anywhere else — it instead
  scans for the `not_at_top` smell. Static site generators behave
  the same way; a `---` block on line 5 is just a horizontal rule.
- **Both close markers honoured.** YAML 1.2 supports `...` as a
  document terminator; some toolchains use `---` for both open and
  close. The validator accepts either as a closer.
- **No PyYAML, by design.** PyYAML accepts tabs in some positions,
  duplicate keys silently, and many "unquoted specials" via
  forgiving scanners. Hugo (`yaml.v3` in Go), Jekyll (Psych in
  Ruby), and Eleventy (`js-yaml` strict mode) do not. We catch what
  the strictest popular consumer would catch.
- **Top-level keys only for duplicate / colon-space checks.** Nested
  values are out of scope — they are too easy to false-positive on
  block scalars and complex flow style.
- **Pure function.** No I/O, no clocks, no transport. The checker
  takes a string and returns a `FrontmatterReport`.
- **Stdlib only.** `dataclasses`, `json`, `sys`. No `re`, no
  third-party YAML parser.

## Composition

- `llm-output-bom-byte-detector` — the BOM check here is narrow (BOM
  inside the frontmatter body). The whole-file BOM check belongs to
  the dedicated detector.
- `llm-output-markdown-fence-orphan-closing-detector` — once
  frontmatter is sound, validate fence delimiters in the body.
- `llm-output-markdown-heading-level-skip-detector` — and then the
  heading tree.
- `prompt-template-versioner` — when this validator starts firing
  on a previously-clean prompt, the version diff is the smoking
  gun.
- `structured-error-taxonomy` — `missing_open`, `missing_close`,
  `not_at_top`, `empty_block`, `bom_in_block` →
  `attribution=model` (regenerate / repair). `tab_indent`,
  `duplicate_key`, `unquoted_special`, `missing_colon_space` →
  `attribution=model` but `severity=warning` for the strict
  pipelines, `severity=error` for Hugo / Jekyll.

## Worked example

Run `python3 example.py` from this directory. Eight cases — two
clean (one with frontmatter, one without) plus one per major
finding family. The runner prints each case as JSON and exits
`1` if any case has a non-empty `findings` list, `0` otherwise.

```
$ python3 example.py
# llm-output-markdown-yaml-frontmatter-validator — worked example

## case 01_clean
input_lines: 9
{ "ok": true, "has_frontmatter": true, "keys": ["title","date","tags"], ... }

## case 02_no_frontmatter_clean
{ "ok": true, "has_frontmatter": false, ... }

## case 03_missing_close
{ "findings": [{"kind":"missing_close","line_no":1,...}], "ok": false }

## case 04_missing_open
{ "findings": [{"kind":"missing_open","line_no":1,...}], "ok": false }

## case 05_not_at_top
{ "findings": [{"kind":"not_at_top","line_no":5,...}], "ok": false }

## case 06_empty_block
{ "findings": [{"kind":"empty_block","line_no":1,...}], "ok": false }

## case 07_dup_and_no_space
{ "findings": [
    {"kind":"duplicate_key","line_no":3,...},
    {"kind":"missing_colon_space","line_no":4,...}
  ], "ok": false }

## case 08_unquoted_special_and_tab
{ "findings": [
    {"kind":"tab_indent","line_no":5,...},
    {"kind":"unquoted_special","line_no":3,...}
  ], "ok": false }
```

Read across the cases: 01 is a fully-formed frontmatter block —
opener on line 1, three keys, well-quoted values, `---` closer. 02
is a doc with no frontmatter at all — the validator passes it
through with `has_frontmatter=False`. 03 catches the most common
LLM bug — opener present, closer forgotten; the entire body is
silently swallowed by the YAML parser. 04 is the inverse — the
model emitted a stray `...` (which is a valid YAML close) on line 1
without a matching opener. 05 catches frontmatter that drifted —
it's correctly delimited but appears after a heading, so no
generator will treat it as metadata. 06 catches the empty-block
case, which renders as a horizontal rule on most setups. 07 folds
two key-shape bugs into one frontmatter — `title` defined twice
(silently de-duplicated) and `tags:python` missing the space after
the colon (parsed as a single literal `tags:python`, not as a key).
08 folds the tab-indent and unquoted-special-character bugs.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(kind, line_no, detail)` before serialisation.

## Exit codes

- `0` — all cases clean.
- `1` — at least one case produced findings (the demo intentionally
  exercises every finding kind, so a normal run exits 1).

When wired into CI as a pre-commit / pre-publish hook, exit 1 means
"reject the document until the frontmatter is repaired."

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.
