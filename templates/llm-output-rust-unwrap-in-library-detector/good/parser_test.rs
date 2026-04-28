// Filename ends with _test.rs — entire file skipped
pub fn boom() {
    let _: i32 = "5".parse().unwrap();
    let _ = std::env::var("Y").expect("Y");
}
