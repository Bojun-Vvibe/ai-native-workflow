# Config loader sketch

Here is a Rust config loader using `?` propagation. The word unwrap
appears in this prose but never as a call.

```rust
use std::collections::HashMap;
use std::fs;
use std::io;

#[derive(Debug)]
enum ConfigError {
    Io(io::Error),
    MissingValue(String),
    BadPort(String),
}

impl From<io::Error> for ConfigError {
    fn from(e: io::Error) -> Self { ConfigError::Io(e) }
}

fn load_config(path: &str) -> Result<HashMap<String, String>, ConfigError> {
    let text = fs::read_to_string(path)?;
    let mut map = HashMap::new();
    for line in text.lines() {
        let mut parts = line.splitn(2, '=');
        let Some(k) = parts.next() else { continue };
        let Some(v) = parts.next() else {
            return Err(ConfigError::MissingValue(k.to_string()));
        };
        map.insert(k.trim().to_string(), v.trim().to_string());
    }
    Ok(map)
}

fn port(map: &HashMap<String, String>) -> Result<u16, ConfigError> {
    let raw = map.get("port").ok_or(ConfigError::MissingValue("port".into()))?;
    raw.parse::<u16>().map_err(|_| ConfigError::BadPort(raw.clone()))
}
```

The string ".unwrap()" inside this prose paragraph should not be flagged
because it is outside any code fence.
