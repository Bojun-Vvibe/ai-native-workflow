# Well-formed tables

| name | role | team |
| ---- | ---- | ---- |
| ada  | eng  | core |
| bob  | pm   | ops  |
| cid  | eng  | core |

Escaped pipes are handled:

| expr        | result |
| ----------- | ------ |
| `a \| b`    | or     |
| `c \| d`    | or     |

Inside a fence, anything goes:

```
| x | y |
| 1 |
```

Done.
