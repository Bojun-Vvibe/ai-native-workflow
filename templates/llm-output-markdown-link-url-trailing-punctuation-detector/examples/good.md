# clean links

Plain link: see [the page](https://example.com/page).

Link followed by a comma outside: [Acme](https://acme.test/foo), then more.

Query string ending in a letter: [search](https://example.com/?q=hello).

Inline code containing a deliberately bad link: `[x](https://example.com/x.)`.

Fenced code with a bad link that must be ignored:

```
[y](https://example.com/y.)
```
