# Clean autolinks

Standard HTTPS: <https://example.com/path?q=1>

Mailto: <mailto:hello@example.org>

Custom but valid scheme: <x-custom-app:open?id=42>

Inline-code documentation about a malformed autolink should NOT trip the
detector: `<://example.com>` and `<3http://x>`.

```markdown
This fenced block also documents <://example.com> and <weird_scheme:y>
without tripping the detector.
```

HTML tags should be ignored: <br>, <img src="x.png">, <a href="y">link</a>.

Generic placeholder with no colon: <List<int>>.
