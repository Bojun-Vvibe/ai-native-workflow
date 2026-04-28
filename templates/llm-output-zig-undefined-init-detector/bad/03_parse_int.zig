const std = @import("std");

pub fn parseInt(s: []const u8) !u64 {
    var result: u64 = undefined;        // BAD: scalar uninit on parse failure
    var maybe: ?u64 = undefined;        // BAD: optional discriminant uninit
    var err_or: anyerror!u64 = undefined; // BAD: error-union tag uninit
    _ = err_or;
    if (s.len == 0) {
        maybe = null;
    } else {
        result = 0;
        for (s) |c| {
            if (c < '0' or c > '9') return error.InvalidChar;
            result = result * 10 + (c - '0');
        }
        maybe = result;
    }
    return maybe orelse error.Empty;
}
