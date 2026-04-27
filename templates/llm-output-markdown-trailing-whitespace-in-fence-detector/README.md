# llm-output-markdown-trailing-whitespace-in-fence-detector

## Problem

Trailing whitespace (spaces or tabs) **inside fenced code blocks** is a
high-signal LLM authoring defect:

- It survives verbatim into the rendered `<pre>` block.
- It corrupts copy-paste of shell snippets (`npm run build·····` ends up
  in the user's terminal as a command with invisible trailing args).
- It breaks byte-for-byte diffs and confuses tools that hash the snippet.
- For YAML / TOML / JSON inside fences, trailing whitespace can flip the
  meaning when the snippet is extracted to a real config file.

Crucially, this is **different** from trailing whitespace on a regular
prose line, where two trailing spaces is the canonical Markdown
hard-line-break syntax. So a generic "no trailing whitespace" linter is
too noisy. This detector targets only the inside-fence case.

## When LLM output triggers it

- The model echoes user-provided shell commands and pads them to align
  visually with surrounding lines.
- Stream-decoded output ends a line on a token boundary that happens to
  include a trailing space.
- The model copies a YAML snippet from a context where the source had
  trailing spaces and faithfully reproduces them inside the fence.

## How the detector works

- Walks the file line by line tracking fence state.
- Recognises `` ``` `` (backtick) and `~~~` (tilde) fences. Closing fence
  must use the same character and be at least as long as the opener
  (CommonMark rule).
- For every line **strictly inside** a fence, checks for trailing space
  or tab characters and reports the column where the trailing run starts
  along with the count of spaces and tabs.
- Lines outside fences are ignored entirely (so hard-break two-space
  endings in prose do not false-positive).
- An unclosed fence at EOF is reported as a separate finding.

## Usage

```sh
python3 detect.py examples/bad-shell-snippet.md examples/good-clean.md
```

Exit codes: `0` clean, `1` trailing whitespace inside a fence (or
unclosed fence at EOF), `2` usage / IO error.

## Worked example

Live run against the four bundled examples:

```
$ python3 detect.py examples/bad-shell-snippet.md examples/bad-multiple-lines.md examples/bad-tilde-fence.md examples/good-clean.md
examples/bad-shell-snippet.md:6:14: trailing whitespace inside fenced code block (3 space(s))
examples/bad-multiple-lines.md:4:17: trailing whitespace inside fenced code block (1 space(s))
examples/bad-multiple-lines.md:5:27: trailing whitespace inside fenced code block (1 tab(s))
examples/bad-multiple-lines.md:6:13: trailing whitespace inside fenced code block (2 space(s))
examples/bad-tilde-fence.md:4:9: trailing whitespace inside fenced code block (2 space(s))
exit=1
```

Running `examples/good-clean.md` on its own:

```
$ python3 detect.py examples/good-clean.md
exit=0
```

That confirms the prose-level hard-break (two trailing spaces on a
non-fence paragraph line) is correctly **not** flagged.

Counts: **3 bad fixtures** (5 findings total), **1 good fixture**
(0 findings).
