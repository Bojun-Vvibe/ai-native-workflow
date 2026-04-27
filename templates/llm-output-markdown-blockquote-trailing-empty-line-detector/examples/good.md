# Good sample

Here is a clean blockquote:

> First sentence.
> Second sentence.

Normal prose follows. Nested quote, also clean:

> Outer quote.
> > Nested line.
> > Another nested line.
> Back to outer.

Single-line quote, no trailing empty marker:

> A pithy one-liner.

A code block that contains the offending pattern is fine, because the
detector is fence-aware:

```text
> A literal quote shown as code.
>
```

End of good sample.
