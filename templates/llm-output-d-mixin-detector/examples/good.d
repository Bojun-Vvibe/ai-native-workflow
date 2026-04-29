// GOOD: no string-mixin sites. Demonstrates legitimate constructs the
// detector must NOT flag.

module good;

import std.stdio : writeln;

// Template mixin (not a string mixin): the argument is an identifier,
// not code text. Must not be flagged.
mixin template Logger(string tag) {
    void log(string msg) { writeln("[", tag, "] ", msg); }
}

class Service {
    mixin Logger!"service";   // template instantiation, no parens-mixin
}

void main() {
    auto s = new Service();
    s.log("hello");

    // Strings that *contain* the word mixin in comments or literals
    // must not trigger the detector.
    auto note = "see also: mixin(...) discussion in docs";
    writeln(note);

    // Suppressed line: an intentional, audited string mixin.
    mixin("int z = 1;");   // mixin-ok: reviewed metaprogramming
    writeln(z);
}

/* A block comment that mentions mixin( should also be ignored. */
/+ Even nested /+ mixin(evil) +/ comments +/

string fn(string s) { return s; }
