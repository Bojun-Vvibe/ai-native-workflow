const std = @import("std");

pub fn pickPointer(want_a: bool, a: *u32, b: *u32) *u32 {
    var p: [*]u8 = undefined;       // BAD: many-pointer uninit
    _ = p;
    var q: ?*u32 = undefined;       // BAD: optional pointer uninit
    if (want_a) q = a else q = b;
    return q.?;
}

pub fn manyPointer(buf: []u8) [*]u8 {
    var ptr: [*]u8 = undefined;     // BAD: many-pointer uninit
    if (buf.len > 0) ptr = buf.ptr;
    return ptr;
}
