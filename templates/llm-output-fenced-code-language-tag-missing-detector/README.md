# llm-output-fenced-code-language-tag-missing-detector

Detect fenced code blocks in markdown that open without a language tag (info
string). Renderers like GitHub, GitLab, MkDocs and most static site generators
rely on the language tag to enable syntax highlighting and copy buttons. LLMs
often emit a mix of tagged and untagged fences in the same document, which
shows up as inconsistent rendering.

## What it flags

Each opening fence (``` ``` ``` or `~~~`) whose info string is empty or
whitespace-only. Closing fences are skipped — only openers are evaluated.

## What it does not flag

- Fences with any non-empty info string (e.g. ` ```py `, ` ```text `, ` ```diff `).
- Inline code spans.
- Lines that look like fences but appear inside an already-open fence (so
  example markdown showing fences inside a fence does not produce noise).

## Usage

```
python3 script.py < your-doc.md
```

Exit code `0` is clean; exit code `1` indicates at least one untagged fence.

## Worked example

Input (`sample-input.txt`):

````
Here is some Python:

```python
def hello():
    return "hi"
```

And here is a snippet without a tag:

```
echo "no tag here"
```

A tilde fence with a tag:

~~~yaml
key: value
~~~

A tilde fence without a tag:

~~~
plain text
~~~

Inline `code` should be ignored.

Final tagged block:

```json
{"ok": true}
```
````

Run:

```
python3 script.py < sample-input.txt
```

Verbatim output:

```
FOUND 2 fence(s) missing a language tag:
  line 10: opening fence '```' has no info string
  line 22: opening fence '~~~' has no info string
```

Exit code: `1`.

The detector correctly skips the tagged ` ```python `, ` ~~~yaml `, and
` ```json ` openers and only flags the two untagged fences.
