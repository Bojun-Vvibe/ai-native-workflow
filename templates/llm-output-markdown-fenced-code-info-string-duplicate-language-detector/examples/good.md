# Clean info strings

Single token:

```python
print("hi")
```

Single token with attributes (no language repeat):

```python title="example.py" linenums=1
print("hi")
```

Different langs in different fences:

```js
console.log("hi");
```

```ts
const x: number = 1;
```

A code block that *contains* what looks like a fence — must not be
flagged because the inner line is inside the outer fence:

````markdown
```python python
inside
```
````

Done.
