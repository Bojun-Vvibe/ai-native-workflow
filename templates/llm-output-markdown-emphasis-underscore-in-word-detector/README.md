# `llm-output-markdown-emphasis-underscore-in-word-detector`

Pure stdlib gate that flags **intra-word underscores in prose** —
`user_id`, `MAX_RETRIES`, `__init__` written *without* backticks —
because non-CommonMark renderers will quietly turn them into
emphasis or bold and *eat the underscores*.

## The bug class

CommonMark says `_` only opens/closes emphasis at word boundaries,
so `snake_case` renders literally. Many real-world renderers
**don't** follow CommonMark on this point:

- Original Markdown.pl, older PHP-Markdown, lots of wikis: render
  `snake_case` as `snake<em>case</em>`.
- Older nbconvert, several Confluence/Slack importers, some
  static-site generators built on legacy parsers: same.
- GitHub-Flavored Markdown got this right ~2017, but offline
  mirrors and downstream tools still ship the old behavior.

The LLM failure path is boring and reliable: the model writes
"set the `user_id`" — except it omits the backticks — and the
production renderer ships `set the user<em>id</em>` to readers.
The author's local CommonMark preview never showed the bug.

## What the detector flags

Three finding kinds, in increasing weirdness:

- `intra_word_underscore` — a single underscore between two word
  characters: `user_id`, `MAX_RETRIES`. Most common.
- `mixed_underscore_word_run` — 2+ underscores in one token:
  `a_b_c_d`. Non-CommonMark renderers tend to *alternate* italic
  segments across these, producing especially ugly output.
- `leading_double_underscore_dunder` — `__name__`-shaped tokens.
  Many renderers turn `__init__` into **bold** `init` and silently
  drop the leading/trailing pairs.

## What the detector ignores (correctly)

- Tokens inside fenced code blocks (` ``` ` and `~~~`).
- Tokens inside inline code spans (` `like_this` `).
- Tokens inside autolinks (`<https://example.invalid/foo_bar>`).
- Tokens inside link URLs (`[text](https://example.invalid/foo_bar)`).
- Indented code blocks (4-space / tab lead).
- Bare leading/trailing underscores (`_word`, `word_`) outside a
  word boundary — those *might* be legitimate emphasis intent.

## When to use

- Pre-publish gate on docs that will be rendered by **multiple**
  pipelines (your site renderer + a downstream wiki + email
  digests). Those pipelines almost never agree on underscore
  emphasis.
- Pre-commit hook on LLM-generated technical writing where
  identifier names appear in prose.
- Audit step on a corpus migration (Confluence -> CommonMark site,
  Notion export -> docs site, etc.) — exactly the path where the
  underscore-emphasis disagreement surfaces.

## The fix is always the same

Wrap the identifier in backticks: `user_id`, `MAX_RETRIES`,
`__init__`. The detector does not auto-fix; it is a gate, and
auto-fixing would risk wrapping things that *should* be emphasis.

## Files

- `detector.py` — single function
  `detect_intra_word_underscores(text: str) -> list[Finding]`.
  Stdlib only. Also runnable as a script:
  `python3 detector.py path/to/file.md`. Exits `0` on no findings,
  `1` otherwise.
- `example.py` — eight worked cases (three clean + five failing
  shapes). Run `python3 example.py`.

## Verified output

The example produces:

- **0 findings** on `01-clean-backticked-identifiers`,
  `05-fenced-code-is-ignored`, `06-inline-code-and-link-urls-ignored`.
- **11 findings** total across cases 02, 03, 04, 07, 08 covering
  all three finding kinds (3 + 3 + 2 + 1 + 2).

## Wiring into a pipeline

```bash
# fail commit if any tracked .md has risky intra-word underscores
git ls-files '*.md' | while read -r f; do
  python3 path/to/detector.py "$f" || exit 1
done
```

## Related templates

- `llm-output-markdown-emphasis-marker-style-consistency-detector` —
  flags inconsistent use of `*` vs `_` for *intentional* emphasis.
  Complementary: this template catches *unintentional* emphasis
  from intra-word underscores.
- `llm-output-markdown-bold-marker-style-consistency-detector` —
  same idea for `**` vs `__`.
