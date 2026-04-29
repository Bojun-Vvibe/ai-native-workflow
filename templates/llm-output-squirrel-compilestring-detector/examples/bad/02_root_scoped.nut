// Root-scoped variant runs in the global root table.
function load_user_hook(src) {
    return ::compilestring(src);
}
