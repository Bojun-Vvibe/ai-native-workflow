# Sample doc with planted empty-link-text findings

See the [docs](https://example.com/docs) for the full guide.

Cite this paper: [](https://example.com/paper-1) — empty text.

Or visit [   ](https://example.com/whitespace) for whitespace.

Try the NBSP form: [ ](https://example.com/nbsp) which is invisible.

Real link: [Example](https://example.com/real) is fine.

Auto-link: <https://example.com/auto> is fine and not in scope.

A reference-style [link][ref] is also fine here, out of scope.

[ref]: https://example.com/ref

Here is a fenced block that should be skipped:

```
[](https://example.com/inside-fence)
[   ](https://example.com/also-inside)
```

Tilde fence too:

~~~
[](https://example.com/tilde-fence)
~~~

But [](https://example.com/after-fence) outside is flagged again.

Two on one line: [](https://a.example) and [ ](https://b.example).

Edge: a literal `[]` with no parens is not a link, ignore.

Edge: [text]() has empty URL — not a finding (URL must be non-empty).
