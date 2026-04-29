// BAD: every `mixin(...)` here parses+compiles a string as D source.
// When the argument is built from a template, file import, or any
// non-literal expression, this is a compile-time eval sink.

module bad;

import std.string : format;
import std.conv : to;

string buildAssign(string name, int v) {
    return format(`int %s = %d;`, name, v);
}

void main(string[] args) {
    // 1. Direct string literal — still flagged (review whether a
    //    proper template would be cleaner).
    mixin("int a = 1 + 2;");

    // 2. Argument is a runtime-built string — true eval-style sink.
    mixin(buildAssign("b", 7));

    // 3. Whitespace and multiline form, also flagged.
    mixin (
        buildAssign("c", 9)
    );

    // 4. Token-string form is just another way to write a string;
    //    the surrounding mixin call is what we flag.
    mixin(q"{int d = 42;}");

    // 5. Template-bang shorthand mixin!"...": the operand is a code
    //    string that becomes D source.
    mixin!"int e = 100;";
}
