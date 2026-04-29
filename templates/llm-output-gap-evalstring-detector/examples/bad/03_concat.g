# Concatenated source — attacker controls the polynomial text.
EvalPoly := function(coeffs)
    local body;
    body := Concatenation("return [", coeffs, "];");
    return EvalString(body);
end;
