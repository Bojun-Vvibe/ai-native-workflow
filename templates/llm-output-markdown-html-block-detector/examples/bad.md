# bad markdown with raw HTML blocks

Some intro paragraph.

<div class="callout">
This is a raw HTML callout.
</div>

A pure-markdown paragraph here.

<table>
  <tr><td>a</td><td>b</td></tr>
</table>

<details>
<summary>Click to expand</summary>
hidden content
</details>

A horizontal rule done as HTML:

<hr/>

Inline HTML mid-paragraph like <br> should NOT be flagged because
this line starts with text, not with a tag.

Inside a fence the HTML must be ignored:

```
<div>ignored</div>
<table></table>
```

An HTML comment is also ignored:

<!-- TODO: revisit this section -->
