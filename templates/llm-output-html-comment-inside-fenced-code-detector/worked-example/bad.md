# Sample doc

Some prose here.

```python
def f():
    <!-- TODO: handle empty -->
    return 1
```

Inline html is fine:

```html
<div>
  <!-- this is legal -->
</div>
```

A JSON sample:

```json
{
  "k": "v"
  <!-- not allowed in JSON -->
}
```

A SQL sample with an unterminated comment:

```sql
SELECT 1;
<!-- still going
SELECT 2;
```

Trailing prose. <!-- this is in prose, not flagged here -->
