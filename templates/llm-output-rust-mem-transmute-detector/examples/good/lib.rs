// Same intents as examples/bad, but using the right tools. No
// findings should be produced from this file.

use std::mem;

pub fn float_bits_to_u64(x: f64) -> u64 {
    x.to_bits()
}

pub fn u64_to_float(x: u64) -> f64 {
    f64::from_bits(x)
}

pub fn bytes_as_str(b: &[u8]) -> Result<&str, std::str::Utf8Error> {
    std::str::from_utf8(b)
}

// Safe helpers that mention transmute only in comments / strings — must
// not be flagged because the tokenizer blanks comments and strings.

pub fn doc_only() {
    // We could call std::mem::transmute here, but we don't.
    let _msg = "std::mem::transmute is dangerous";
}

// Other `mem::*` calls are fine and must not be flagged.
pub fn swap_two(a: &mut i32, b: &mut i32) {
    mem::swap(a, b);
}

pub fn replace_value(slot: &mut String, new: String) -> String {
    mem::replace(slot, new)
}

pub fn size_only<T>() -> usize {
    mem::size_of::<T>()
}

// User-defined helper named `transmute` outside any unsafe context.
// The bare-name detector requires `unsafe` in scope, so this must
// not be flagged.
fn transmute(x: i32) -> i32 { x + 1 }

pub fn use_helper() -> i32 {
    transmute(41)
}

// Suppression marker: load-bearing FFI shim that has been reviewed.
pub fn reviewed_ffi(p: *const u8) -> *const i8 {
    unsafe { std::mem::transmute(p) } // llm-allow:mem-transmute
}
