// Mentions inside comments are ignored.
// Avoid compilestring(src) on untrusted input.
/* compilestring(x) is a foot-gun. */
# compilestring(y) line comment
function add(a, b) { return a + b; }
