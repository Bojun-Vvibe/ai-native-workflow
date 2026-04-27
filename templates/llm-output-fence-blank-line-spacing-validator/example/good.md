# Release Notes

The new retry policy is documented below.

The function returns a tuple of `(ok, error)`:

```python
def call():
    return True, None
```

After the call, you can inspect the result.

## Configuration

The config block follows.

```yaml
retries: 3
backoff: exponential
```

The defaults are conservative.
