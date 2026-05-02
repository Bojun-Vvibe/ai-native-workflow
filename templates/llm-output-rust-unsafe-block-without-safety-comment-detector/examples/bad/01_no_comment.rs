use std::slice;

pub fn read_first(ptr: *const u8, len: usize) -> u8 {
    unsafe {
        let s = slice::from_raw_parts(ptr, len);
        s[0]
    }
}
