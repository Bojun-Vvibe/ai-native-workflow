# Consistent blockquote spacing

> First quote, one space after marker.
> Second line, same style.

Some prose in between.

> Another quote.
> Still one space after every `>` marker.
>
> Even the empty quote line above is fine — empty lines don't count toward
> the style vote.

> > Nested quotes also use one space consistently.
> > Both inner and outer.

Even with content like `>foo` mentioned inline as code, that's not a
blockquote line so it's ignored: `>foo`.
