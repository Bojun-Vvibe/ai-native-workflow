# Quick demo

Three typoed languages, one canonical, one alias, one unknown-but-far-from-known.

```pyhton
print("hello")
```

```javscript
console.log("hi");
```

```tyepscript
const x: number = 1;
```

```python
print("ok")
```

```py
print("ok")
```

```myorglang
:: not a real language but not close to one either
```

A fenced block whose body contains a fake fence opener should NOT be
re-flagged:

````markdown
```pyhton
this is a code sample showing what NOT to do
```
````
