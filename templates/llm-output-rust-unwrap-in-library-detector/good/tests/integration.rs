// File path includes `tests/` directory — entire file skipped
// (place this under tests/integration.rs in a real crate)
pub fn helper() -> i64 {
    let n: i64 = "7".parse().unwrap();
    n + std::env::var("X").expect("X").len() as i64
}
