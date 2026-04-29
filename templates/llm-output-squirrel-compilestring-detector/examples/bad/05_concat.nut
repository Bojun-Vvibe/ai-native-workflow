// Concatenated source, attacker controls the tail.
function eval_expr(expr) {
    local body = "return (" + expr + ")";
    return compilestring(body)();
}
