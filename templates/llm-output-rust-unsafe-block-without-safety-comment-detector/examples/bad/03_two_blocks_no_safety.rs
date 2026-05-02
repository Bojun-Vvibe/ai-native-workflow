pub struct Buf {
    ptr: *mut u8,
    len: usize,
}

impl Buf {
    #[inline]
    pub fn write_zero(&mut self) {
        unsafe { core::ptr::write_bytes(self.ptr, 0, self.len) }
    }

    pub fn read_at(&self, i: usize) -> u8 {
        unsafe { *self.ptr.add(i) }
    }
}
