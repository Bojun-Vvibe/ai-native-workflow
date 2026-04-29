# Mentions inside `#` comments are ignored.
# Avoid EvalString(s) on attacker-controlled strings.
# ReadAsFunction(InputTextString(s)) is the read-string variant.
Add2 := function(a, b) return a + b; end;
