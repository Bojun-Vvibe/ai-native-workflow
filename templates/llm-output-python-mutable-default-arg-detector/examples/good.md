# Good examples — safe defaults

These blocks all defend against the mutable-default footgun, either
by using the ``None`` sentinel pattern or by sticking to immutable
default values.

## 1. Sentinel pattern for a list parameter

```python
def append_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```

## 2. Sentinel pattern for a dict parameter

```python
def memo(x, cache=None):
    if cache is None:
        cache = {}
    if x in cache:
        return cache[x]
    cache[x] = x * x
    return cache[x]
```

## 3. Immutable defaults are fine

```python
def greet(name, greeting="hello", times=1, suffix=("!",)):
    return [f"{greeting}, {name}{suffix[0]}" for _ in range(times)]
```

## 4. Frozenset and None and numeric defaults

```python
def filter_known(items, allowed=frozenset({1, 2, 3}), limit=None):
    out = []
    for it in items:
        if limit is not None and len(out) >= limit:
            break
        if it in allowed:
            out.append(it)
    return out
```

## 5. A non-Python block that should be ignored entirely

```bash
# this is shell, not python — the detector must skip it
default=()
echo "${default[@]:-}"
```

## 6. A pseudo-code block tagged python that does not parse — skipped

```python
def explain(x):
    <perform some side-effect>
    return ???
```
