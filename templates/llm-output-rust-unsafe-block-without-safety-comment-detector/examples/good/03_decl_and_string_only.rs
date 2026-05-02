// Declarations are intentionally NOT flagged: only `unsafe { ... }`
// blocks (callers of unsafe) require the SAFETY comment.

pub unsafe fn raw_dance(_p: *mut u8) {
    // body intentionally empty
}

pub unsafe trait MyMarker {}

unsafe impl MyMarker for u32 {}

extern "C" {
    pub fn libc_strlen(s: *const u8) -> usize;
}

// String literal containing the keyword should not trip the detector.
pub fn message() -> &'static str {
    "this string mentions unsafe { fake_block } but is just text"
}
