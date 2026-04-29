// the substring "Machine.add(" appears only inside a string literal
// describing the API, never as an actual call. Should NOT be flagged.
"Use Machine.add(path) to load a patch at runtime." => string doc;
<<< doc >>>;
