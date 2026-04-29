// Compile-then-call in one expression, the canonical eval pattern.
local result = compilestring("return 1+2")();
print(result);
