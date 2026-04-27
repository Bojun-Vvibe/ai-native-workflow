# Fenced code info string duplications

Plain repeat:

```python python
print("hi")
```

Alias repeat (py == python):

```python py
print("hi")
```

Decorator repeat:

```javascript language=javascript
console.log("hi");
```

Bracketed alias:

```bash (sh)
echo hi
```

Triple alias group (sh, bash, shell all collapse):

```sh bash shell
echo hi
```

A clean fence for control:

```yaml
key: value
```
