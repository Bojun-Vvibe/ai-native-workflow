# clean markdown without raw HTML blocks

Some intro paragraph.

> This is a markdown blockquote callout.

A pure-markdown paragraph here.

| col a | col b |
| ----- | ----- |
| a     | b     |

**Click to expand**: hidden content described in markdown instead of
a `<details>` block.

A horizontal rule done in markdown:

---

Inline `<br>` mention inside backticks is fine and would not be
flagged anyway.

Inside a fence the HTML is ignored:

```
<div>ignored</div>
<table></table>
```

An HTML comment is also ignored:

<!-- TODO: revisit this section -->
