const std = @import("std");

const Node = struct { value: i64, next: ?*Node };

pub fn head(list: ?*Node) ?*Node {
    var ptr: *Node = undefined; // BAD: dangling pointer if list is null
    if (list) |n| ptr = n else return null;
    return ptr;
}

pub fn firstValue(list: ?*Node) i64 {
    var v: i64 = undefined;     // BAD: scalar uninit
    if (list) |n| v = n.value;
    return v;
}
