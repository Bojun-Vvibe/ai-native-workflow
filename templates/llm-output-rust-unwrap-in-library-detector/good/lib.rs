// lib code with `?` propagation — no unwrap/expect at all
use std::io;

pub fn read_first_line(p: &str) -> io::Result<String> {
    let s = std::fs::read_to_string(p)?;
    Ok(s.lines().next().unwrap_or("").to_string())
}

pub fn parse(s: &str) -> Result<i64, std::num::ParseIntError> {
    s.trim().parse::<i64>()
}
