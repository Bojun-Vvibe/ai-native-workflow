# llm-output-markdown-autolink-bare-url-style-mix-detector

A small python3 stdlib linter that flags markdown files which mix the
autolink style (`<https://example.com>`) with the bare URL style
(`https://example.com`) for plain URL references.

## What defect this catches

LLM-generated markdown frequently drifts mid-document between rendering URLs
as autolinks (angle-bracket form) and as bare text URLs. Both render in most
viewers, but mixing them looks inconsistent and breaks tooling that expects
one style. This detector flags any document that contains **both** styles.

URLs inside inline links — `[text](https://example.com)` — are correctly
ignored, since those are neither bare nor autolink form.

## When to use

Run as a post-generation lint step on any markdown asset produced by an LLM
where consistent URL rendering matters: changelogs, OSS READMEs, generated
docs, release notes.

## Inputs / outputs

- **Input**: one markdown file path.
- **Output (stdout)**: a one-line summary plus per-occurrence locations.
- **Exit code**: `1` if both styles co-occur in the same file, `0` otherwise,
  `2` on bad usage.

Code fences, tilde fences, and inline backtick spans are stripped before
analysis, so example URLs inside code blocks do not trigger findings.

## Usage

```
python3 detect.py path/to/file.md
echo "exit=$?"
```

## Worked example

The `worked-example/` subdir contains a deliberately inconsistent `bad.md`
and the expected detector output. Verify with:

```
python3 detect.py worked-example/bad.md > /tmp/out.txt; echo "exit=$?"
diff worked-example/expected-output.txt /tmp/out.txt
```

`diff` should print nothing and the script should exit `1`.
