# bad.md — 4 intentional findings

Block 1 — a single line mixes tabs and spaces in its leading
whitespace (mixed_in_line):

```python
def f(x):
	    return x + 1
```

Block 2 — block_mixed: first indented line is space-led, second is
tab-led (each line internally pure):

```python
def g(x):
    if x:
	return 1
    return 0
```

Block 3 — TWO mixed_in_line findings on consecutive lines:

```python
class C:
	    a = 1
 	b = 2
```

Block 4 — clean python (0 findings here):

```python
def h(x):
    return x * 2
```
