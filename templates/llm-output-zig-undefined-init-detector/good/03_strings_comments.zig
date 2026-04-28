const std = @import("std");

// String / comment content that mentions `undefined` should not trip
// the scanner. The masking pass blanks these out.

pub fn warn() void {
    const msg = "var x: u32 = undefined; // do not write this";
    std.debug.print("{s}\n", .{msg});
    // var x: u32 = undefined; <- inside a // comment, should not match
}

pub fn multiline() []const u8 {
    return
        \\var trap: i64 = undefined;
        \\var also: *u8 = undefined;
        \\const c: bool = undefined;
    ;
}
