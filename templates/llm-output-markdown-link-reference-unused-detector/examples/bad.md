# Worked example: bad

This document defines several reference labels but only uses some of them.

See the [project homepage][home] and the [API reference][api] for details.

A second paragraph mentions [the changelog][changelog].

[home]: https://example.com/
[api]: https://example.com/api
[changelog]: https://example.com/changelog
[contributing]: https://example.com/contributing
[license]: https://example.com/license
[deprecated-spec]: https://example.com/old

Inside a fenced code block, definitions and refs should be ignored:

```markdown
[fake]: https://nope.example/
See [stuff][fake].
```

The `[contributing]: ...`, `[license]: ...`, and `[deprecated-spec]: ...`
definitions above are dangling — nothing in the prose links to them.
