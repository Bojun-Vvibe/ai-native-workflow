# good: structurally similar YAML with no duplicate keys.

Top-level mapping, all keys unique:

```yaml
name: my-service
replicas: 3
image: nginx:1.25
port: 8080
```

Nested mapping with environment variables — every key is distinct:

```yaml
spec:
  containers:
    - name: web
      env:
        LOG_LEVEL: info
        DB_URL: postgres://db/app
        PORT: "8080"
```

Two list items with the same key `name:` — these are NOT duplicates,
because each `- ` opens a fresh mapping scope:

```yaml
services:
  - name: api
    port: 8000
  - name: worker
    port: 9000
```

Multi-document stream — same key appears in each document, but that
is allowed because `---` resets scope:

```yml
foo: 1
bar: 2
---
foo: 3
bar: 4
```
