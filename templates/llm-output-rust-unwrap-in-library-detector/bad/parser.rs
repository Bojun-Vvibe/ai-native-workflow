// parser — expect with a message that contains the word "unwrap" in a comment
// the LLM left this `.expect(...)` even though `?` would compose better
pub fn first_int(s: &str) -> i64 {
    s.split(',').next().expect("at least one field expected").trim().parse::<i64>().expect("not an int")
}
