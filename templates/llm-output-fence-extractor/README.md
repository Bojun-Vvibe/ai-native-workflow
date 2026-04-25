# llm-output-fence-extractor

A small, stdlib-only extractor that pulls fenced code blocks out of LLM markdown output and survives the messes models actually produce: nested fences, tilde fences, attribute-laden language tags, and **truncated final blocks** the model never closed.

## The problem

"Just regex `\`\`\`(.*?)\`\`\`` it" works for one happy-path example and breaks the moment a real LLM hands you a response. The failure modes are boring but consistent:

- The model wraps a `markdown` example in a 4-backtick fence so it can show 3-backtick blocks inside. A 3-backtick regex returns the *inner* block as the outer block, with garbage prose stripped from the front.
- The model writes `~~~` fences (CommonMark-legal tildes) instead of backticks. Backtick-only extractors silently return zero blocks.
- The model decorates the language tag: `python {.numberLines}`, `python:`, `python,`. Now your `if block.lang == "python"` filter fails for two thirds of valid blocks.
- The model gets cut off by a token limit mid-block. There is no closing fence. A regex with non-greedy `.*?` returns nothing, so the partial code (often the most interesting part of the response) is silently lost. A greedy regex returns *every block plus all prose between them*, which is worse.
- The fence is indented by two spaces because it is inside a Markdown list. Strict CommonMark parsers still recognize this; naive regexes do not.

You hit these the moment you build any of: a code-only-please tool, a "save this snippet to a file" command, a JSON-extractor that has to ignore code, an eval harness that compares model code to a reference.

## The shape of the solution

`extract_blocks(text) -> list[CodeBlock]` returns a stable, structured list with everything a downstream caller needs:

```text
CodeBlock(
    lang:       str   # normalized: "python", or "" if no tag
    info:       str   # full info string after the fence ("python {.numberLines}")
    body:       str   # block contents, joined with "\n", no trailing newline magic
    fence_char: str   # "`" or "~"
    fence_len:  int   # 3, 4, 5, ...   (matters for nested-fence reasoning)
    indent:     str   # leading whitespace stripped from body lines
    start_line: int   # 1-based, opening fence line in source
    end_line:   int   # 1-based, closing fence line (or last line if unterminated)
    terminated: bool  # was a matching closing fence found?
)
```

The two pieces callers consistently want and rarely get from "just a regex" are **`fence_len`** (so nested fences work — a 4-backtick block is closed only by 4+ backticks, never by an internal 3-backtick line) and **`terminated`** (so a truncated tail can be flagged for a re-prompt or repair pass instead of silently being treated like a clean block).

## Conventions implemented

- Fence char is `` ` `` or `~`. Fences must be 3+ chars; closing fence must be the same char and **>=** the opening length.
- Up to 3 leading spaces of indent on the opening fence are tolerated (CommonMark behavior). The same indent is stripped from each body line.
- Language tag normalization: take the first whitespace-delimited token, drop any `{...}` attribute suffix, drop trailing `,;:`, lowercase. So `python {.numberLines}` → `python`, `Python:` → `python`.
- `only_lang=""` selects blocks with no language tag.
- The opening fence line and closing fence line are not part of `body`.
- An unterminated final block still produces a `CodeBlock` with `terminated=False`. Callers decide whether to use the partial code, discard it, or trigger a continuation prompt.

## When to use it

- Any tool that consumes LLM markdown and only wants the code: code-runners, save-to-file commands, eval harnesses, diff appliers.
- Filtering by language ("only run the `bash` blocks") in agent tool surfaces.
- Detecting truncation in long generations: a `terminated=False` final block is a strong signal to either re-prompt with continuation or fail loudly rather than ship a half-snippet.

## When NOT to use it

- If you need a full CommonMark AST (link references, list nesting, HTML blocks, etc.), use a real parser like `markdown-it-py` or `mistune`. This template covers fenced blocks specifically and intentionally nothing else.
- For *streaming* extraction during generation, this batch API is the wrong shape — a streaming extractor needs an incremental state machine. Use this once the response is finalized.
- For non-fenced "indented code blocks" (4-space-indent style). Models almost never emit those; this template ignores them on purpose.

## Failure modes the implementation defends against

1. **Nested fences.** Outer 4-backtick wrapper containing inner 3-backtick blocks returns one outer `CodeBlock` with the inner fences preserved verbatim in `body`.
2. **Tilde fences.** `~~~` is recognized; mixing tildes and backticks across blocks works.
3. **Decorated language tags.** Normalized as documented above; the original raw tag stays available via `info`.
4. **Truncated final block.** Returned with `terminated=False` so callers can branch.
5. **Empty body.** Allowed; returned as `body=""`.
6. **No fences at all.** Returns an empty list, never raises.

## Files in this template

- `fence_extractor.py` — stdlib-only reference (~110 lines).
- `worked_example.py` — six real LLM-output shapes: plain, nested, tilde, no-lang, weird-info-string, truncated. Plus assertions for filtering and `extract_first`.

## Sample run

```text
== plain ==
  found 1 block(s)
  [0] lang='python' info='python' fence=``` lines=3-6 terminated=True first_body_line='def add(a, b):'
== nested ==
  found 1 block(s)
  [0] lang='markdown' info='markdown' fence=```` lines=3-11 terminated=True first_body_line='Some prose.'
== tilde ==
  found 1 block(s)
  [0] lang='ruby' info='ruby' fence=~~~ lines=1-3 terminated=True first_body_line='puts "tildes work"'
== no_lang ==
  found 1 block(s)
  [0] lang='' info='' fence=``` lines=1-4 terminated=True first_body_line='just a plain block'
== weird_info ==
  found 2 block(s)
  [0] lang='python' info='python {.numberLines startFrom=1}' fence=``` lines=1-3 terminated=True first_body_line='x = 1'
  [1] lang='python' info='python:' fence=``` lines=5-7 terminated=True first_body_line='y = 2'
== truncated ==
  found 1 block(s)
  [0] lang='python' info='python' fence=``` lines=1-4 terminated=False first_body_line='def slow():'

All assertions passed.
```

The truncated sample is the one that justifies the template's existence: a naive regex returns nothing for that input. Here the half-finished `def slow()` body is preserved with `terminated=False` so the caller can choose to repair, re-prompt, or discard.
