# Clean Document

This file has only well-formed links and should produce zero findings.

- Inline link: [click here](https://example.com).
- Inline image: ![logo](https://example.com/logo.png).
- Reference link: [docs][r1].
- Collapsed reference: [home][].
- Empty link text (intentionally not flagged): [](https://example.com).
- All-whitespace text (intentionally not flagged): [   ](https://example.com).
- Inline code that mentions a link: `[ x ](url)` is code, not a link.

```
[ inside fence ](https://example.com)
```

[r1]: https://example.com/r1
[home]: https://example.com/
