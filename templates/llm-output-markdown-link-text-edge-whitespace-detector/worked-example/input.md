# Visible Edge Whitespace Demo

A clean inline link looks like [click here](https://example.com).
A bad inline link looks like [ click here ](https://example.com).
Another bad one with only trailing space: [docs ](https://example.com/docs).
And one with only leading space: [ home](https://example.com/).

Reference-style is checked too: [ ref text][r1] should flag.
Image alt text counts as well: ![ logo ](https://example.com/logo.png).

These should NOT flag:

- Empty link text: [](https://example.com).
- All-whitespace link text: [   ](https://example.com).
- Inline code containing brackets: `[ not a link ](url)` is just code.

```
[ this is inside a fence ](https://example.com)
```

[r1]: https://example.com/r1
