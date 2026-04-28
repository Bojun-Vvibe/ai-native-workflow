# Good examples — strict equality everywhere

These blocks use only ``===`` / ``!==`` (or do not use equality at
all), so the detector should produce zero findings.

## 1. Strict equality with explicit zero

```javascript
function isEmpty(count) {
    if (count === 0) {
        return true;
    }
    return false;
}
```

## 2. Status-code comparison with strict operators

```js
function classify(resp) {
    if (resp.code === 200) return "ok";
    if (resp.code !== 200) return "err";
    return "unknown";
}
```

## 3. Replace the ``== null`` idiom with an explicit null/undefined check

```typescript
function pick<T>(a: T | null | undefined, b: T): T {
    if (a === null || a === undefined) return b;
    if (a === b) return a;
    return a;
}
```

## 4. Equality-looking strings, regexes, and comments are ignored

```jsx
function render(n) {
    const label = `count == ${n}`;          // template literal — ignored
    const re = /count != 0/;                // regex literal — ignored
    // a comment with == and != inside it is ignored
    const ok = n === 1 ? "one" : "many";    // strict — fine
    return label + " " + ok + " " + re.source;
}
```

## 5. A non-JS block that should be skipped entirely

```python
# this is python; the detector must skip it because the tag is not js/ts
if x == 1:
    print("one")
```

## 6. A js block with no equality at all

```js
function add(a, b) {
    return a + b;
}
```
