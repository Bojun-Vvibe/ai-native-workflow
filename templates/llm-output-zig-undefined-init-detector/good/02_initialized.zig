const std = @import("std");

// Initialize scalars with real values, not `undefined`.
pub fn countWords(s: []const u8) u32 {
    var count: u32 = 0;
    if (s.len == 0) return count;
    var i: usize = 0;
    while (i < s.len) : (i += 1) {
        if (s[i] == ' ') count += 1;
    }
    return count + 1;
}

pub fn flag(predicate: bool) bool {
    var result: bool = false;
    if (predicate) result = true;
    return result;
}
