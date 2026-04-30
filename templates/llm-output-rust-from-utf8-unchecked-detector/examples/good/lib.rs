// Good fixtures: nothing here should be flagged.

use std::io::Read;

// 1. Use the safe Result-returning constructor.
pub fn safe_parse(b: &[u8]) -> Option<&str> {
    std::str::from_utf8(b).ok()
}

// 2. Validate first, then call the unchecked variant. The detector
// looks for evidence of a from_utf8 call earlier in the same scope.
pub fn validated(b: &[u8]) -> &str {
    let _checked = std::str::from_utf8(b).expect("must be UTF-8");
    unsafe { std::str::from_utf8_unchecked(b) }
}

// 3. is_ascii() is also accepted as evidence — ASCII implies UTF-8.
pub fn ascii_only(b: &[u8]) -> &str {
    assert!(b.is_ascii());
    unsafe { std::str::from_utf8_unchecked(b) }
}

// 4. simdutf8 fast-path validation.
pub fn simd_validated(b: &[u8]) -> &str {
    // Pretend simdutf8 is in scope.
    let _ok = simdutf8::basic::from_utf8(b).expect("must be UTF-8");
    unsafe { std::str::from_utf8_unchecked(b) }
}

// 5. utf8_chunks() iteration also counts as validation evidence.
pub fn chunked(b: &[u8]) -> usize {
    let _: usize = b.utf8_chunks().count();
    let s = unsafe { std::str::from_utf8_unchecked(b) };
    s.len()
}

// 6. Suppression marker — author has signed off.
pub fn signed_off(b: &[u8]) -> &str {
    // llm-allow:from-utf8-unchecked
    unsafe { std::str::from_utf8_unchecked(b) }
}

// 7. Comment that mentions from_utf8_unchecked must NOT trip the
// detector — comments are blanked.
//
// Bad example for docs: unsafe { std::str::from_utf8_unchecked(b) }

/* Block comment with the same: unsafe { std::str::from_utf8_unchecked(b) } */

// 8. String literal that contains the call must NOT trip.
pub fn doc_string() -> &'static str {
    "see also: unsafe { std::str::from_utf8_unchecked(b) }"
}
