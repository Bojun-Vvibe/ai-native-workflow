# Bad sample

Here is a quote that ends with empty `>` lines:

> First sentence of the quote.
> Second sentence.
>
>

After the quote, normal prose resumes. Another offender below uses a
nested blockquote that also leaves trailing empties.

> Outer quote level.
> > Nested quote line.
> >
>

And one more, single-line quote followed by a stray empty marker:

> Just one line.
>

End of bad sample.

```text
> This is inside a fenced code block.
>
>
```

The fenced block above must NOT trigger; it shows the very pattern as
a code example.
