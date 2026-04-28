# A short config example

Here is the proposed shape:

```yaml
service:
  name: ingest
  retries:
    timeout_s: 30
    max: 5
  endpoints:
    - /a
    - /b
```

Use it as a starting point.
