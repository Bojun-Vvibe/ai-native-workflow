// Trailing-comment style: SAFETY justification on the same line.
pub fn read_byte(p: *const u8) -> u8 {
    unsafe { *p } // SAFETY: caller upholds dereference precondition
}

#[allow(unsafe_code)]
pub fn touch(p: *mut u8) {
    // SAFETY: `p` is exclusively borrowed for the duration of this fn.
    #[inline(never)]
    unsafe { core::ptr::write_volatile(p, 0) }
}
