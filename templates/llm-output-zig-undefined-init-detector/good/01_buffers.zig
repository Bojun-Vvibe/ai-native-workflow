const std = @import("std");

// Legitimate: large stack buffer about to be filled by a single OS call.
pub fn readLine(reader: anytype) ![]u8 {
    var buf: [4096]u8 = undefined;
    const n = try reader.read(&buf);
    return buf[0..n];
}

// Legitimate: array used as scratch space for fmt.bufPrint.
pub fn formatU64(value: u64) ![]u8 {
    var scratch: [32]u8 = undefined;
    return std.fmt.bufPrint(&scratch, "{}", .{value});
}
