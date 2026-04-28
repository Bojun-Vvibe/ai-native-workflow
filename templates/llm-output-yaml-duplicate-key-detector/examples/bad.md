# bad: many duplicate-key cases that real YAML parsers silently swallow.

Plain duplicate at the top level:

```yaml
name: my-service
replicas: 3
name: other-service
image: nginx:1.25
```

Duplicate inside a nested mapping (`env:`):

```yaml
spec:
  containers:
    - name: web
      env:
        LOG_LEVEL: info
        DB_URL: postgres://db/app
        LOG_LEVEL: debug
        PORT: "8080"
```

Duplicate inside a sequence-of-mappings entry — second `name:` shadows
the first within the same list item:

```yaml
services:
  - name: api
    port: 8000
    name: api-v2
  - name: worker
    port: 9000
```

Duplicate after a `---` document break should NOT be flagged across
the boundary, but the duplicate *within* the second doc should be:

```yml
foo: 1
bar: 2
---
baz: 1
baz: 2
```
