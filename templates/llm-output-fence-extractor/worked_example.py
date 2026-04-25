"""Worked example for llm-output-fence-extractor.

Six scenarios, each is a real LLM-output shape we've seen in the wild:

  1. Plain ```python block, normal close.
  2. Outer 4-backtick wrapper with an inner 3-backtick block (nested).
  3. Tilde fences (~~~).
  4. No language tag.
  5. Language tag with attributes ("python {.numberLines}") + trailing colon.
  6. Truncated final block (model ran out of tokens, no closing fence).

Run:
    python3 worked_example.py
"""

from __future__ import annotations

from fence_extractor import extract_blocks, extract_first


SAMPLES = {
    "plain": """\
Here is the code:

```python
def add(a, b):
    return a + b
```

Done.
""",
    "nested": """\
Outer wrapper that itself contains a fenced block:

````markdown
Some prose.

```python
print("inner")
```

More prose.
````
""",
    "tilde": """\
~~~ruby
puts "tildes work"
~~~
""",
    "no_lang": """\
```
just a plain block
no language tag
```
""",
    "weird_info": """\
```python {.numberLines startFrom=1}
x = 1
```

```python:
y = 2
```
""",
    "truncated": """\
```python
def slow():
    # model ran out of tokens before closing the fence
    items = [
""",
}


def report(name: str, text: str) -> None:
    print(f"== {name} ==")
    blocks = extract_blocks(text)
    print(f"  found {len(blocks)} block(s)")
    for i, b in enumerate(blocks):
        first = b.body.splitlines()[0] if b.body else ""
        print(
            f"  [{i}] lang={b.lang!r} info={b.info!r} "
            f"fence={b.fence_char * b.fence_len} "
            f"lines={b.start_line}-{b.end_line} "
            f"terminated={b.terminated} first_body_line={first!r}"
        )


def assertions() -> None:
    # 1. plain
    blocks = extract_blocks(SAMPLES["plain"])
    assert len(blocks) == 1
    assert blocks[0].lang == "python"
    assert blocks[0].terminated
    assert blocks[0].body == "def add(a, b):\n    return a + b"

    # 2. nested: outer 4-backtick wrapper contains inner 3-backtick block
    blocks = extract_blocks(SAMPLES["nested"])
    assert len(blocks) == 1, f"expected 1 outer block, got {len(blocks)}"
    assert blocks[0].lang == "markdown"
    assert blocks[0].fence_len == 4
    assert "```python" in blocks[0].body
    assert "print(\"inner\")" in blocks[0].body

    # 3. tilde
    blocks = extract_blocks(SAMPLES["tilde"])
    assert len(blocks) == 1 and blocks[0].lang == "ruby" and blocks[0].fence_char == "~"

    # 4. no lang
    blocks = extract_blocks(SAMPLES["no_lang"])
    assert len(blocks) == 1 and blocks[0].lang == ""

    # 5. weird info strings normalize
    blocks = extract_blocks(SAMPLES["weird_info"])
    assert len(blocks) == 2
    assert blocks[0].lang == "python"
    assert blocks[0].info == "python {.numberLines startFrom=1}"
    assert blocks[1].lang == "python"  # "python:" -> "python"

    # 6. truncated final block
    blocks = extract_blocks(SAMPLES["truncated"])
    assert len(blocks) == 1
    assert blocks[0].terminated is False
    assert blocks[0].lang == "python"
    assert "items = [" in blocks[0].body

    # Filtering
    only_py = extract_blocks(SAMPLES["weird_info"], only_lang="python")
    assert len(only_py) == 2
    only_rb = extract_blocks(SAMPLES["weird_info"], only_lang="ruby")
    assert len(only_rb) == 0

    # extract_first convenience
    first = extract_first(SAMPLES["plain"], lang="python")
    assert first is not None and first.body.startswith("def add")


if __name__ == "__main__":
    for name, text in SAMPLES.items():
        report(name, text)
    print()
    assertions()
    print("All assertions passed.")
