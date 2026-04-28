# good.md — 0 findings

Pure-space block:

```python
def f(x):
    if x:
        return 1
    return 0
```

Pure-tab block:

```python
def g(x):
	if x:
		return 1
	return 0
```

Blank lines (no indent at all, ignored):

```python
def h():
    pass

    return None
```

Non-python fence is ignored entirely:

```ruby
def f
	  puts "mix" # ignored
end
```
