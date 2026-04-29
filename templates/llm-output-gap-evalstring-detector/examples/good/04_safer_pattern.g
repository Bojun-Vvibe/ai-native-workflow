# Safer pattern: dispatch on a small fixed table of operations.
DispatchOp := function(op, a, b)
    if   op = "+" then return a + b;
    elif op = "-" then return a - b;
    elif op = "*" then return a * b;
    elif op = "/" then return a / b;
    fi;
    Error("unknown op: ", op);
end;

Print(DispatchOp("+", 1, 2), "\n");
