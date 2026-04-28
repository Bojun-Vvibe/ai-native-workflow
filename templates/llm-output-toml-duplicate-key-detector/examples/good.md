# Service config (clean)

```toml
[package]
name = "widget"
version = "0.1.0"

[server]
host = "0.0.0.0"
port = 8080

[database]
# 'name' here does NOT collide with [package].name — different scope.
name = "primary"
url = "postgres://x"
```

Same key in array-of-tables, distinct elements:

```toml
[[mirror]]
url = "https://a"

[[mirror]]
url = "https://b"
```

Comment containing `=` should not be parsed as a key:

```toml
[meta]
note = "key = value inside string is fine"
# port = 9999  -- commented out, not a real assignment
```
