# Bad examples — mutable default arguments

This document shows the classic Python footgun that LLMs love to
emit: a mutable container as a default argument value.

## 1. The textbook list-default bug

```python
def append_item(item, bucket=[]):
    bucket.append(item)
    return bucket
```

## 2. The "memoization" dict-default bug

```python
def memo(x, cache={}):
    if x in cache:
        return cache[x]
    cache[x] = x * x
    return cache[x]
```

## 3. Set literal default + factory call default

```python
def collect(items, seen={0}, log=list()):
    for it in items:
        if it not in seen:
            seen.add(it)
            log.append(it)
    return log


def make_index(rows, idx=defaultdict(list)):
    for k, v in rows:
        idx[k].append(v)
    return idx
```

## 4. Keyword-only default and async def

```python
async def fetch(url, *, headers={"x-trace": "1"}):
    return (url, headers)
```
