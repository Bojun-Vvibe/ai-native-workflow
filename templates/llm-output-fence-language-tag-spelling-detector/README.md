# llm-output-fence-language-tag-spelling-detector

Detects fenced code block language tags that look like typos of a known
language (e.g. ` ```pyhton ` -> `python`, ` ```javscript ` -> `javascript`,
` ```bsh ` -> `bash`).

This complements `llm-output-code-fence-language-tag-validator` (which checks
presence / allowlist membership) by suggesting the *intended* tag using a
bounded Levenshtein distance against a built-in canonical set.

## How it works

- Scan line-by-line, tracking fence open/close state (` ``` ` or `~~~`).
- For each opening fence with a tag, if the tag is **not** in the canonical
  allowlist, compute edit distance against every known tag.
- If a known tag is within edit distance 2, emit a finding with a suggestion.

Pure Python stdlib. Deterministic.

## Run

```bash
python3 detector.py path/to/file.md [more.md ...]
```

Exit code:
- `0` — no findings
- `1` — at least one suspected misspelling
- `2` — usage error

## Example output

Running against the bundled `examples/bad.md`:

```
$ python3 detector.py examples/bad.md
examples/bad.md:5: misspelled fence tag 'pyhton' -> did you mean 'python'?
examples/bad.md:11: misspelled fence tag 'javscript' -> did you mean 'javascript'?
examples/bad.md:17: misspelled fence tag 'bsh' -> did you mean 'bash'?

3 finding(s).
$ echo $?
1
```

And `examples/good.md` exits `0` with no output.

## Tuning

- Edit `KNOWN_TAGS` in `detector.py` to add project-specific languages
  (e.g. `mermaid`, `plantuml`, `solidity`).
- The edit-distance cap is `2`. Bump to `3` if your inputs are noisier;
  drop to `1` for stricter behavior.

## Limitations

- Will not flag a tag that is simply unknown but not close to any known
  tag (use the validator template for allowlist enforcement).
- Tags that are real-but-rare (e.g. `q`, `j`) may not appear in the
  default allowlist; extend `KNOWN_TAGS` to silence them.
