const std = @import("std");

pub fn averageOrZero(xs: []const f64) f64 {
    var avg: f64 = undefined;   // BAD: scalar uninit when xs is empty
    if (xs.len == 0) return avg;
    var sum: f64 = 0;
    for (xs) |x| sum += x;
    avg = sum / @as(f64, @floatFromInt(xs.len));
    return avg;
}

pub fn flag(predicate: bool) bool {
    var result: bool = undefined; // BAD: bool uninit
    if (predicate) result = true;
    return result;
}
