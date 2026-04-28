// helper module — unwrap on Option in shared utility code
pub fn first_word(s: &str) -> &str {
    s.split_whitespace().next().unwrap()
}

pub fn must_decode(b: &[u8]) -> String {
    String::from_utf8(b.to_vec()).unwrap()
}
