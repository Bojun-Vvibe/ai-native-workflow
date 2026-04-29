// Safer pattern: a tiny interpreter over a fixed grammar.
function eval_op(op, a, b) {
    switch (op) {
        case "+": return a + b;
        case "-": return a - b;
        case "*": return a * b;
        case "/": return a / b;
    }
    throw "unknown op: " + op;
}

local r = eval_op("+", 1, 2);
print(r);
