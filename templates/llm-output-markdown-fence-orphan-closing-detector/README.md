# llm-output-markdown-fence-orphan-closing-detector

Pure stdlib detector that scans a markdown document produced by an
LLM for orphaned, unterminated, or mismatched fenced-code-block
delimiters. The failure mode it catches: the model emits an answer
that *parses* (the renderer does not crash) but renders
unrecognisably, because a single stray ` ``` ` or `~~~` line silently
turns the rest of the document into a grey code block.

These bugs are pernicious in long answers: an orphan delimiter on
line 30 of a 500-line response mass-converts everything after it.
Downstream consumers — RAG chunkers that split on prose vs. code,
syntax-highlighting frontends, screen readers — all degrade in
different, equally-confusing ways.

## Why a separate template

Existing fence-related siblings cover adjacent concerns:

- `llm-output-fence-extractor` — *pulls out* fenced code blocks for
  downstream processing. Assumes the fences are well-formed. This
  template is the upstream gate that proves they are.
- `llm-output-fence-language-tag-spelling-detector` — looks at the
  info string after the opener (`python` vs `pyhton`). This template
  looks at the delimiter *structure* itself.
- `llm-output-fence-mismatched-tilde-backtick-detector` — flags
  whole-document statistics (e.g. the doc mixes both styles). This
  template does per-pair matching: opener-and-closer must use the
  same marker family.
- `llm-output-fence-info-string-trailing-comma-detector` — punctuation
  smell on the info string. Orthogonal.
- `llm-output-fence-blank-line-spacing-validator` — whitespace around
  the fence. Orthogonal.

## Findings

Deterministic order: `(kind, line_no, detail)` — two runs over the
same input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `unterminated_open` | a fence is opened and the document ends without ever closing it; everything after the opener is silently rendered as code |
| `orphan_close` | a fence-line appears that cannot be paired with any opener and is not inside any tracked fence span |
| `marker_mismatch` | a fence-line that *would* close the open fence uses the wrong marker family (` ``` ` vs `~~~`); CommonMark requires the closer to use the same marker character as the opener |
| `count_mismatch` | a fence-line uses fewer marker chars than the opener (e.g. opener is ```` ```` ````, would-be closer is ` ``` `); the shorter run does NOT close the block |
| `info_on_close` | the closing fence carries an info string (` ```python `); closers must be bare or behaviour is renderer-defined |

`ok` is `False` iff any finding fires.

## Design choices

- **CommonMark-correct fence parser.** A fence line is 3+ runs of
  the same marker character (` ` ` or `~`), with up to 3 leading
  spaces of indent. More than 3 leading spaces makes it an indented
  code block, not a fence, and it is ignored. Backtick fences whose
  info string contains a backtick are not fences (CommonMark §4.5).
- **Closer rules are strict.** Same marker family, run length `>=`
  opener's run, and no info string. A line that fails any of these
  while a fence is open is reported as `marker_mismatch`,
  `count_mismatch`, or `info_on_close` and the fence stays open
  (lenient) for `info_on_close`, stays open (strict) for the others
  — matching the renderer behaviour they actually exhibit.
- **First-pass pairing, second-pass orphan sweep.** The forward pass
  builds the `(open, close)` pairs greedily. The second pass walks
  fence-lines again and reports any that are neither a tracked open
  nor close *and* not inside a tracked span — those are true
  orphans. In practice the unterminated-open case dominates because
  a stray fence at top level just becomes the next opener.
- **No fence-content parsing.** The detector does not look inside
  fences. It only cares about delimiters.
- **Pure function.** No I/O, no clocks, no transport. The checker
  takes a string and returns a `FenceReport`.
- **Stdlib only.** `dataclasses`, `json`, `sys`. No `re`, no
  third-party markdown parser.

## Composition

- `llm-output-fence-extractor` — run this validator first; only
  hand well-formed inputs to the extractor.
- `llm-output-fence-language-tag-spelling-detector`,
  `llm-output-fence-info-string-trailing-comma-detector` — once
  delimiter structure is sound, layer the info-string validators.
- `prompt-template-versioner` — when this validator starts firing on
  a previously-clean prompt, the version diff is the smoking gun.
- `structured-error-taxonomy` — `unterminated_open`,
  `orphan_close`, `marker_mismatch`, `count_mismatch` →
  `attribution=model` (regenerate / repair). `info_on_close` →
  `attribution=model` but `severity=warning` (most renderers
  tolerate it).

## Worked example

Run `python3 example.py` from this directory. Six cases — one clean
doc plus one per finding family. The runner prints each case's
findings as JSON and exits `1` if any case has a non-empty
`findings` list, `0` otherwise.

```
$ python3 example.py
# llm-output-markdown-fence-orphan-closing-detector — worked example

## case 01_clean
input_lines: 13
{ "fences": [...two paired fences...], "findings": [], "ok": true }

## case 02_unterminated_open
{ "findings": [{"kind":"unterminated_open","line_no":3,...}], "ok": false }

## case 03_orphan_close
{ "findings": [{"kind":"unterminated_open","line_no":5,...}], "ok": false }

## case 04_marker_mismatch
{ "findings": [{"kind":"marker_mismatch","line_no":5,...}], "ok": false }

## case 05_count_mismatch
{ "findings": [{"kind":"count_mismatch","line_no":5,...}], "ok": false }

## case 06_info_on_close
{ "findings": [{"kind":"info_on_close","line_no":5,...}], "ok": false }
```

Read across the cases: 01 is the only clean doc — two well-formed
fences, one backtick, one tilde. 02 is the classic "model forgot to
close the fence" — everything after line 3 would render as code in
GitHub. 03 is the practical orphan-close: a single ` ``` ` appears
mid-doc, and because nothing was open, it *opens* a new fence that
never closes. 04 catches the mixed-marker bug — a ` ``` ` opener
followed by a `~~~` line; the `~~~` is not a valid closer, so the
fence stays open and the would-be closer ` ``` ` on line 7 finally
ends it. 05 catches the count bug — a 4-tick opener with embedded
3-tick lines that look like closers but aren't. 06 catches the
sloppy "I'll repeat the language tag on the closer" smell.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(kind, line_no, detail)` before serialisation.

## Exit codes

- `0` — all cases clean.
- `1` — at least one case produced findings (the demo's only
  non-clean case is case 01, so a normal run exits 1).

When wired into CI as a pre-commit / pre-publish hook, exit 1 means
"reject the document until the fences are repaired."

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.
