#!/usr/bin/env julia
# Bad fixture: 5+ instances of dynamic-code execution that should each be flagged.

user_input = length(ARGS) > 0 ? ARGS[1] : "1 + 1"

# 1: classic eval(Meta.parse(...)) — TWO findings on this line
result = eval(Meta.parse(user_input))
println(result)

# 2: include_string runs the string as Julia source
include_string(Main, "x_runtime = 42")
println(x_runtime)

# 3: @eval macro to define a function from a runtime symbol
fname = Symbol("fn_" * user_input)
@eval $(fname)(x) = x * 2

# 4: fully-qualified Core.eval
Core.eval(Main, Meta.parse("y_runtime = 7"))   # TWO findings on this line
println(y_runtime)

# 5: Base.eval used as a "looser" alias
Base.eval(Main, :(z_runtime = 99))
println(z_runtime)

# 6: Meta.parse alone — flagged because it almost always pairs with eval
expr = Meta.parse("3 + 4")
println(eval(expr))   # TWO findings: Meta.parse line above + eval here
