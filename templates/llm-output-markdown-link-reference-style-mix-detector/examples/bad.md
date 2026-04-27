# Notes on Markdown Links

The [CommonMark spec](https://spec.commonmark.org) defines two link forms.
Most authors use one consistently, but LLM output often mixes them.

For more background see the [GitHub Flavored Markdown][gfm] notes and
the [original Gruber syntax][gruber-md].

You can also visit [Daring Fireball](https://daringfireball.net) for the
historical context, or read the [pandoc documentation](https://pandoc.org)
on link extensions.

A shortcut reference like [example][] is also reference-style, and so is
[bare shortcut] when paired with a definition.

```python
# This [link](http://nope.example) is inside a code fence and MUST be ignored.
print("hello")
```

Inline `code with [brackets](nope)` should also be ignored.

[gfm]: https://github.github.com/gfm/
[gruber-md]: https://daringfireball.net/projects/markdown/
[example]: https://example.com
[bare shortcut]: https://example.org
