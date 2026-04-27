# Bad example — fragmented blockquotes

The following quote should be one continuous blockquote with two paragraphs,
but the author left a fully blank line between the `>` lines:

> First paragraph of the quote, which sets up the topic.

> Second paragraph that the author intended as a continuation, but
> CommonMark treats this as a brand-new blockquote.

Another instance further down:

> Authors who forget the bare `>` marker

> end up with two adjacent quotes that render with a visible gap.

Inside a fence, blank lines between `>` lines must be ignored:

```
> sample one

> sample two
```

End of file.
