# llm-output-code-fence-language-tag-validator

Pure stdlib validator for Markdown fenced code blocks (triple-backtick
or triple-tilde) in LLM prose. Catches the silent-corruption class
where the model emits a code block but forgets the language tag, uses
inconsistent tag styles across the same document (`py` here,
`python` there), uses a tag that does not match the actual content
(a `python` tag on what is obviously a JSON object), or leaves an
opening fence unclosed.

Renderers happily display the block either way, so the bug is
invisible to the human reviewer of the rendered output. The cost
shows up downstream in syntax-highlighters, doc-search indexers,
"copy as code" UI affordances, and ML pipelines that route by
language tag.

## Why a separate template

Existing siblings cover adjacent surfaces:

- `llm-output-fence-extractor` — extracts fenced spans for downstream
  processing. Says nothing about tag quality or fence pairing.
- `llm-output-markdown-heading-level-skip-detector` — same family
  (Markdown structural discipline) but for headings.
- `llm-output-list-marker-consistency-validator` — same family for
  bullet markers.

This template plugs the gap. Run it before publishing the prose, or
gate it on every reviewer-loop turn so the model's bad habits surface
within the same conversation.

## Findings

Deterministic order: `(kind, line, detail)` — two runs over the same
input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `missing_language_tag` | opening fence has no tag (only when `require_language_tag=True`, the default) |
| `non_lowercase_tag` | `Python` instead of `python` — same language, but breaks an `inconsistent_tag_style` check on the next document |
| `suspicious_tag_whitespace` | tag contains an internal space — almost always a typo (` python` / `python 3`) |
| `unknown_tag` | tag not in caller-supplied `allowed_tags` set (only when caller passes one) |
| `tag_content_mismatch` | tag claims one language but the body has unambiguous markers of another (a `python` block whose body is JSON; a `json` block whose body is not JSON-shaped; a `bash` block whose body is Python or JSON) |
| `inconsistent_tag_style` | the same logical language is tagged two different ways across the document (`py` and `python` together; `sh` and `bash` together) |
| `unclosed_fence` | an opening fence with no matching closer (CommonMark fence-pairing: same character, same indent, length ≥ opener's length, empty tag-part on the closer) |

`ok` is `False` iff any finding fires.

## Design choices

- **CommonMark fence-pairing.** The state machine tracks the opening
  fence's character (`` ` `` vs `~`), its indent column, and its run
  length. A closer must match all three (and have an empty tag-part)
  — anything else is body content. This is what lets case 08 pass:
  a tilde-fenced block whose body contains a literal triple-backtick
  line is *not* a fence terminator.
- **Content-mismatch heuristics are conservative.** The validator
  only fires `tag_content_mismatch` when the body has an unambiguous
  signal in the *opposite* direction — a `{...}` JSON object with a
  `"key":` pair, a Python `def`/`class`/`import`/`from` statement, a
  recognizable shell command head. The cost of a false positive is
  high (an annoying gate that the model fights), so the heuristics
  err on the side of silence.
- **`inconsistent_tag_style` canonicalizes via a small map.**
  `py`/`python3` collapse to `python`; `sh`/`shell`/`zsh` collapse
  to `bash`. If a document uses both `py` and `python`, the finding
  cites the variants — the fix is to pick one and stick with it.
- **Eager refusal on bad input.** `prose` not a `str` raises
  `FenceValidationError` immediately. Empty prose is *valid* (zero
  fences, zero findings).
- **One forward scan, no regex.** Single pass, line-by-line, with a
  small "inside a fence?" state machine.
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json`. No `re`.

## Composition

- `llm-output-fence-extractor` — run *after* this template. This one
  validates fence shape and tag quality; the extractor pulls the
  bodies out for downstream syntax-aware processing.
- `llm-output-list-marker-consistency-validator` — same family, run
  both as a "Markdown structural hygiene" gate.
- `llm-output-jsonschema-repair` — a `tag_content_mismatch` finding
  on a `json` block (body is not JSON-shaped) is the cheapest
  trigger to escalate to schema repair.
- `agent-decision-log-format` — one log line per finding sharing
  `line` so a reviewer can jump to the offending row.
- `structured-error-taxonomy` — `missing_language_tag` /
  `non_lowercase_tag` / `inconsistent_tag_style` → prompt-template
  hygiene bug; `unclosed_fence` → the model truncated mid-block,
  retry with a fresh window; `tag_content_mismatch` → the model
  picked the wrong language label, often a sign the upstream prompt
  was ambiguous.

## Worked example

Run `python3 example.py` from this directory. Eight cases — two
clean (a tagged Python block, plus the tricky tilde-fenced block
that contains a literal triple-backtick line in the body) and six
each demonstrating a distinct finding family. The output below is
captured verbatim from a real run.

```
# llm-output-code-fence-language-tag-validator — worked example

## case 01_clean_python
kwargs: {}
prose:
  | Here is a snippet:
  | ```python
  | def add(a, b):
  |     return a + b
  | ```
{
  "fences": 1,
  "findings": [],
  "ok": true,
  "tags_seen": [
    "python"
  ]
}

## case 02_missing_tag
kwargs: {}
prose:
  | Untagged block:
  | ```
  | print('hi')
  | ```
{
  "fences": 1,
  "findings": [
    {
      "detail": "opening fence has no language tag",
      "kind": "missing_language_tag",
      "line": 2
    }
  ],
  "ok": false,
  "tags_seen": []
}

## case 03_inconsistent_tag_style
kwargs: {}
prose:
  | First:
  | ```py
  | x = 1
  | ```
  | 
  | Second:
  | ```python
  | y = 2
  | ```
{
  "fences": 2,
  "findings": [
    {
      "detail": "language 'python' tagged as ['py', 'python'] in the same document",
      "kind": "inconsistent_tag_style",
      "line": 0
    }
  ],
  "ok": false,
  "tags_seen": [
    "py",
    "python"
  ]
}

## case 04_tag_content_mismatch_python_is_json
kwargs: {}
prose:
  | Mismatch:
  | ```python
  | {"name": "alice", "age": 30}
  | ```
{
  "fences": 1,
  "findings": [
    {
      "detail": "tag 'python' but body parses as JSON",
      "kind": "tag_content_mismatch",
      "line": 2
    }
  ],
  "ok": false,
  "tags_seen": [
    "python"
  ]
}

## case 05_unclosed_fence
kwargs: {}
prose:
  | Open and never closed:
  | ```bash
  | echo hello
{
  "fences": 1,
  "findings": [
    {
      "detail": "opening fence at line 2 never closed (char='`', len=3)",
      "kind": "unclosed_fence",
      "line": 2
    }
  ],
  "ok": false,
  "tags_seen": [
    "bash"
  ]
}

## case 06_unknown_tag_with_allowlist
kwargs: {"allowed_tags": ["bash", "json", "python", "sql"]}
prose:
  | Custom DSL:
  | ```myql
  | SELECT 1;
  | ```
{
  "fences": 1,
  "findings": [
    {
      "detail": "tag 'myql' not in allowed set ['bash', 'json', 'python', 'sql']",
      "kind": "unknown_tag",
      "line": 2
    }
  ],
  "ok": false,
  "tags_seen": [
    "myql"
  ]
}

## case 07_non_lowercase_tag
kwargs: {}
prose:
  | Caps:
  | ```Python
  | print(1)
  | ```
{
  "fences": 1,
  "findings": [
    {
      "detail": "tag 'Python' is not lowercase (prefer 'python')",
      "kind": "non_lowercase_tag",
      "line": 2
    }
  ],
  "ok": false,
  "tags_seen": [
    "Python"
  ]
}

## case 08_tilde_fence_with_inner_backticks
kwargs: {}
prose:
  | Tilde-fenced block that contains a triple-backtick line in the body:
  | ~~~markdown
  | Use ``` to start a code fence.
  | ~~~
{
  "fences": 1,
  "findings": [],
  "ok": true,
  "tags_seen": [
    "markdown"
  ]
}
```

The output above is byte-identical between runs — `_CASES` is a fixed
list, the validator is a pure function, and findings are sorted by
`(kind, line, detail)` before serialisation.

## Files

- `example.py` — the validator + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.
