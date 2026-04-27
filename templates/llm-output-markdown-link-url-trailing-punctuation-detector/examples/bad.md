# bad links

Sentence with stray period inside URL: see [the page](https://example.com/page.).

Comma trapped: see [Acme](https://acme.test/foo,) and the rest.

Multiple offenders on one line: [a](https://x.test/a;) then [b](https://y.test/b!).

A question mark trap: [docs](https://example.com/?q=hi?).

This one is fine: [the page](https://example.com/page).

Inline code with a fake bad link: `[x](https://example.com/x.)` — should be ignored.

Inside a fence the bad link is also ignored:

```
[y](https://example.com/y.)
```
