const std = @import("std");

pub fn countWords(s: []const u8) u32 {
    var count: u32 = undefined; // BAD: read-before-write on empty input
    if (s.len == 0) return count;
    var i: usize = 0;
    count = 0;
    while (i < s.len) : (i += 1) {
        if (s[i] == ' ') count += 1;
    }
    return count + 1;
}
