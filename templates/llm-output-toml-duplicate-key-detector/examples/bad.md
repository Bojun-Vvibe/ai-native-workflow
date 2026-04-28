# Service config

Here's the config the model produced:

```toml
[package]
name = "widget"
name = "gizmo"
version = "0.1.0"

[server]
host = "0.0.0.0"
port = 8080
port = 8081
```

And an inline mistake elsewhere:

```toml
[database]
url = "postgres://x"
url = "postgres://y"
```

Note: the same key `name` is fine if it's in two different tables —
that's tested in good.md.
