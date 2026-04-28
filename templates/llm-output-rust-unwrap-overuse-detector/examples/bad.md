# Config loader sketch

Here is a quick Rust config loader. I leaned on `unwrap` for brevity.

```rust
use std::fs;
use std::collections::HashMap;

fn load_config(path: &str) -> HashMap<String, String> {
    let text = fs::read_to_string(path).unwrap();
    let mut map = HashMap::new();
    for line in text.lines() {
        let mut parts = line.splitn(2, '=');
        let k = parts.next().unwrap().trim().to_string();
        let v = parts.next().expect("missing value").trim().to_string();
        map.insert(k, v);
    }
    map
}

fn port(map: &HashMap<String, String>) -> u16 {
    map.get("port").unwrap().parse::<u16>().unwrap()
}

fn must_get(map: &HashMap<String, String>, key: &str) -> String {
    map.get(key)
        .cloned()
        .unwrap_or_else(|| panic!("missing key: {}", key))
}
```

Note: the literal "this should not unwrap" is just prose, not code.
