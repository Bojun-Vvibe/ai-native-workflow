# llm-output-markdown-atx-heading-trailing-hash-style-mix-detector

Detect inconsistent ATX heading trailing-hash style within a single
markdown document.

CommonMark allows two ATX heading forms that render identically:

- **Open style** — `## Foo`
- **Closed style** — `## Foo ##` (optional trailing hashes)

LLMs sometimes mix the two within one document. The render is fine but
the source is inconsistent and many style guides (and `markdownlint`
rule MD003) require a single form throughout.

## What it flags

The detector treats whichever style appears in the **first** ATX
heading as the document's chosen style, then flags every subsequent
heading using the other form.

## What it does not flag

- Setext headings (`===` / `---` underlines) — out of scope here
- ATX-looking lines inside fenced code blocks (` ``` ` or `~~~`)
- ATX-looking lines indented 4+ spaces (those are indented code blocks)
- Documents containing zero ATX headings

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any flagged heading is found, `0` otherwise.

## Verify against the worked example

Bad input (intentional violations):

```
$ python3 script.py < worked-example/input.md
dominant ATX heading style: open (set by line 1)
line 7: closed style heading breaks consistency: '## Background ##'
line 15: closed style heading breaks consistency: '#### Sub-details ####'
line 23: closed style heading breaks consistency: '##### Wrap-up #####'
$ echo $?
1
```

Clean input (single style):

```
$ python3 script.py < worked-example/clean.md
$ echo $?
0
```

You can also diff against the recorded expected output:

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff.
