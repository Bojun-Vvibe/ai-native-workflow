// Loop reads scripts from an array of strings and runs each.
foreach (src in scripts) {
    local f = compilestring(src);
    f();
}
