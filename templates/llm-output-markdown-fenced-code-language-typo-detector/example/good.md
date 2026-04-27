# Clean demo

All language tags are canonical or known aliases, and the nested fence
inside the outer ```` ```` block is not re-scanned.

```python
print("hello")
```

```javascript
console.log("hi");
```

```typescript
const x: number = 1;
```

```bash
echo ok
```

````markdown
```pyhton
This typoed tag lives inside an OUTER fenced block, so the detector
must not flag it. That is the whole point of being code-fence-aware.
```
````

Done.
