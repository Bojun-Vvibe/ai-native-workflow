// All unwraps are inside `#[cfg(test)] mod tests { ... }` — must be skipped
pub fn double(x: i32) -> i32 {
    x * 2
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn doubles() {
        let r = Some(3).map(double).unwrap();
        assert_eq!(r, 6);
    }

    #[test]
    fn parses() {
        let v: i32 = "42".parse().expect("must parse");
        assert_eq!(v, 42);
    }
}
