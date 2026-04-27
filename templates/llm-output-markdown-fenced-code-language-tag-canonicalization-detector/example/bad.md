## Sample doc

Here is some Python:

```py
print("hello")
```

And some shell:

```sh
echo hi
```

And then later, more Python — but with a different tag:

```python3
print("again")
```

YAML config:

```yml
key: value
```

A Node snippet:

```js
console.log(1)
```

Already-canonical tag (should NOT be flagged):

```python
print("ok")
```

Unknown tag (should NOT be flagged here — different detector handles spelling):

```mystery-lang
???
```
