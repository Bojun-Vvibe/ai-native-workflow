// `.unwrap()` only mentioned in comments and string literals — must not trip
pub fn describe() -> &'static str {
    // never call `.unwrap()` in library code; prefer `?` propagation
    let msg = "do not use .unwrap() or .expect(\"x\") here";
    msg
}

pub fn raw_doc() -> &'static str {
    r#"this raw string says .unwrap() but it is not code"#
}

pub fn raw_hashes() -> &'static str {
    r##"contains "quotes" and .expect("oops") in a raw string"##
}
