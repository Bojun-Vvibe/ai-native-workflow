// Bad fixtures: every from_utf8_unchecked call here must be flagged.

use std::io::Read;

// 1. Direct call on raw bytes from stdin — no validation.
pub fn read_stdin_as_str() -> String {
    let mut buf = Vec::new();
    std::io::stdin().read_to_end(&mut buf).unwrap();
    let s: &str = unsafe { std::str::from_utf8_unchecked(&buf) };
    s.to_string()
}

// 2. Network bytes wrapped directly.
pub fn parse_packet(payload: &[u8]) -> &str {
    unsafe { std::str::from_utf8_unchecked(payload) }
}

// 3. String::from_utf8_unchecked on a Vec<u8> from FFI.
pub fn ffi_to_string(raw: Vec<u8>) -> String {
    unsafe { String::from_utf8_unchecked(raw) }
}

// 4. Bare from_utf8_unchecked after a use.
use std::str::from_utf8_unchecked;
pub fn quick(b: &[u8]) -> &str {
    unsafe { from_utf8_unchecked(b) }
}

// 5. File read into a buffer, then handed straight to the unsafe ctor.
pub fn slurp_file(path: &str) -> String {
    let bytes = std::fs::read(path).unwrap();
    let s = unsafe { std::str::from_utf8_unchecked(&bytes) };
    s.to_string()
}

// 6. Inside an unsafe fn body via an inner unsafe block — also flagged.
pub unsafe fn outer(b: &[u8]) -> &str {
    let inner = b;
    unsafe { std::str::from_utf8_unchecked(inner) }
}
