// Realistic LLM-generated Rust that reaches for `transmute` instead of
// the right tool. Every call site below is a finding.

use std::mem;

pub fn float_bits_to_u64(x: f64) -> u64 {
    // Wrong: should be `x.to_bits()`.
    unsafe { std::mem::transmute(x) }
}

pub fn u64_to_float(x: u64) -> f64 {
    unsafe { mem::transmute(x) }
}

pub fn bytes_as_str(b: &[u8]) -> &str {
    // Wrong: should be `std::str::from_utf8(b).unwrap()`.
    unsafe { std::mem::transmute::<&[u8], &str>(b) }
}

pub unsafe fn fn_ptr_cast(f: extern "C" fn() -> i32) -> usize {
    // `unsafe fn` body — no `unsafe { }` needed, still flagged.
    transmute(f)
}

pub fn copy_repr_c<T: Copy, U: Copy>(src: &T) -> U {
    unsafe { mem::transmute_copy::<T, U>(src) }
}

pub fn extend_lifetime<'a, 'b>(s: &'a str) -> &'b str {
    // Classic LLM mistake: forging a longer lifetime.
    unsafe { core::mem::transmute::<&'a str, &'b str>(s) }
}

pub fn reinterpret_slice(input: &[u32]) -> &[u8] {
    unsafe {
        std::mem::transmute::<&[u32], &[u8]>(input)
    }
}
