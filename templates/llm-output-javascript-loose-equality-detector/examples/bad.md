# Bad examples — JavaScript loose equality

Each block below uses ``==`` or ``!=`` in real code positions, so the
detector should flag them.

## 1. The classic count-equals-zero coercion bug

```javascript
function isEmpty(count) {
    if (count == 0) {
        return true;
    }
    return false;
}
```

## 2. Status code and string-vs-number comparison

```js
function classify(resp) {
    if (resp.code == 200) return "ok";
    if (resp.code != 200) return "err";
    return "unknown";
}
```

## 3. Mixed loose and strict, plus loose-eq-null idiom

```typescript
function pick<T>(a: T | null, b: T): T {
    if (a == null) return b;     // common idiom; flagged with reason=loose_eq_null
    if (a === b) return a;       // strict — fine, not flagged
    if ((a as any) == "yes") return b;  // loose — flagged
    return a;
}
```

## 4. Operators inside template literals and regexes must be ignored

```jsx
function render(n) {
    const label = `count == ${n}`;          // inside template literal; ignored
    const re = /==/;                        // regex literal; ignored
    // a comment with == inside it should also be ignored
    const ok = n == 1 ? "one" : "many";     // real loose-eq; flagged
    return label + " " + ok + " " + re.source;
}
```
