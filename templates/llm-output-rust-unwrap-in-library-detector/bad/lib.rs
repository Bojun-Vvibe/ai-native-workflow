// lib.rs — straightforward unwrap in library function
use std::collections::HashMap;

pub fn lookup(map: &HashMap<String, u32>, key: &str) -> u32 {
    *map.get(key).unwrap()
}

pub fn parse_port(s: &str) -> u16 {
    s.parse::<u16>().expect("invalid port")
}
