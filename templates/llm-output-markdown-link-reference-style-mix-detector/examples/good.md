# Notes on Markdown Links

The [CommonMark spec](https://spec.commonmark.org) defines a link form
that most authors use consistently.

For more background see the [GitHub Flavored Markdown](https://github.github.com/gfm/)
notes and the [original Gruber syntax](https://daringfireball.net/projects/markdown/).

You can also visit [Daring Fireball](https://daringfireball.net) for the
historical context, or read the [pandoc documentation](https://pandoc.org)
on link extensions.

```python
# This [link][nope] is inside a code fence and MUST be ignored.
print("hello")
```

Inline `code with [brackets][nope]` should also be ignored.
