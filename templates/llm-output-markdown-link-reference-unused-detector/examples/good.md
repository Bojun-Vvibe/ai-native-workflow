# Worked example: good

Every reference definition below is consumed by the prose.

See the [project homepage][home] and the [API reference][api] for details.

A second paragraph mentions [the changelog][changelog] and the
[contributing guide][contributing], plus the [license][license].

[home]: https://example.com/
[api]: https://example.com/api
[changelog]: https://example.com/changelog
[contributing]: https://example.com/contributing
[license]: https://example.com/license

Fenced code with ref-like syntax must not affect the count:

```markdown
[orphan]: https://nope.example/
See [stuff][orphan].
```
