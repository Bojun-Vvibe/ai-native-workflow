// Comments mention doString("evil " .. x) and doFile(path) but no
// runtime evaluation actually happens.
/* Lobby doString(src) -- documented elsewhere, never called here. */
greet := method(name, writeln("hello, ", name))
greet("world")
