# Notes

The function ` foo` returns 42, while `bar ` is deprecated.

This phrase ` baz ` is doubly wrong.

But this one is fine: the literal `` ` `` represents a single backtick.

Inside a fenced block we should NOT flag anything:

```
some ` weird ` text inside a fence
```

After the fence, ` qux` should still trigger.
