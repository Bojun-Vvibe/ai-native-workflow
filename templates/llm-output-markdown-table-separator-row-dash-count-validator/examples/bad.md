# bad table separator rows

Uneven dash counts below.

| col a | col b | col c |
| --- | -- | ------ |
| 1 | 2 | 3 |

Another bad one with alignment colons:

| left | center | right |
|:---|:--:|----:|
| a | b | c |

This one is fine and should NOT be flagged:

| x | y |
| --- | --- |
| 1 | 2 |

Inside a fence the bad row should be ignored:

```
| a | b |
| --- | -- |
```
