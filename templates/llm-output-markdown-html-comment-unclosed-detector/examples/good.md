# Worked example: good

Intro paragraph.

<!-- TODO: rewrite the section below before publishing -->

A multi-line comment that is properly closed:

<!--
internal note: review with the docs team
before the next release.
-->

Inline code mentioning the syntax should not confuse the detector:
the literal `<!--` and `-->` tokens here are wrapped in backticks.

A fenced block discussing comments should also be ignored:

```html
<!-- this is just an example, never closed inside the fence
```

## Heading after the fenced block

Body content renders normally.
