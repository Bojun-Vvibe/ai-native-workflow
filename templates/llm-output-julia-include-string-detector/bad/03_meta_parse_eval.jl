function eval_expr(s::String)
    # classic two-step: parse a string, then eval the AST
    expr = Meta.parse(s)
    return eval(expr)
end

# inline form is the same sink
quick(s) = eval(Meta.parse(s))
