# Documentation-only mention of the dangerous APIs in a comment.
# We avoid include_string(...) and Meta.parse(...) because they accept strings.
# Use eval on a literal Expr built at compile time instead:
function add_method!()
    expr = :(square(x) = x * x)
    eval(expr)  # evaluating a literal AST is fine
end
