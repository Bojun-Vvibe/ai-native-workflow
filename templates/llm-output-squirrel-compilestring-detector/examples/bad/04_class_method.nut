// Inside a class method, source comes from a config table.
class Hook {
    function run(cfg) {
        local closure = compilestring(cfg.script);
        return closure();
    }
}
