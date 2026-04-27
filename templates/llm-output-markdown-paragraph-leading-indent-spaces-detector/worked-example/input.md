A normal paragraph that starts at column zero.

 This paragraph has one accidental leading space.

  Another paragraph with two leading spaces, which renders fine
  but the source is misleading.

   Three leading spaces here — still a paragraph in CommonMark,
   not a code block.

    This is four spaces and IS a code block, so it should NOT flag.

- A list item is fine
  - Nested list item is fine
- Back to top level

> A blockquote is fine
  > Even this indented one (the > marker is the block construct)

# Heading is fine
 ## Indented heading is also a valid construct, skipped

Normal paragraph again.

```
 indented line inside fence — ignored
  also ignored
```

 Final flagged line with one space.
