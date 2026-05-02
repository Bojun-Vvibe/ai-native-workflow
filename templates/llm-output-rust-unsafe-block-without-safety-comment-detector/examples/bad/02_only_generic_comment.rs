// Helper that reinterprets bytes as a u32 little-endian.
pub fn from_le(bytes: &[u8]) -> u32 {
    // The caller guarantees bytes.len() >= 4.
    let p = bytes.as_ptr() as *const u32;
    unsafe { p.read_unaligned() }.to_le()
}
