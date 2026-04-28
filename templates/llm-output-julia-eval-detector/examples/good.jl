#!/usr/bin/env julia
# Good fixture: same intents as bad.jl, expressed without dynamic-code execution.

user_op = length(ARGS) > 0 ? ARGS[1] : "double"

# Dispatch table instead of eval(Meta.parse(...)):
const OPS = Dict{String, Function}(
    "double" => x -> x * 2,
    "square" => x -> x * x,
    "negate" => x -> -x,
)

if haskey(OPS, user_op)
    println(OPS[user_op](7))
else
    error("unknown op: $user_op")
end

# Multiple dispatch instead of @eval / runtime-defined methods:
struct Rect; w::Float64; h::Float64; end
struct Circ; r::Float64; end
area(s::Rect) = s.w * s.h
area(s::Circ) = 3.14159 * s.r * s.r
println(area(Rect(2.0, 3.0)))
println(area(Circ(1.5)))

# getfield is the safe lookup for a *whitelisted* function name:
const ALLOWED = Set([:sin, :cos, :tan])
fname = :sin
if fname in ALLOWED
    f = getfield(Base, fname)
    println(f(0.0))
end

# Mention of "eval" inside a # comment must not trigger:
# We deliberately avoid eval / Meta.parse / include_string here.

# Mention of "eval(" inside a string literal must not trigger:
doc = "Avoid eval(Meta.parse(input)) and include_string for user data."
println(doc)

# Triple-quoted string containing the words must not trigger:
big_doc = """
Note: eval(...) and Meta.parse(...) and @eval are unsafe with user input.
Use a Dict dispatch table instead.
"""
println(big_doc)

# An intentional, audited eval can be suppressed inline:
const _STARTUP = eval(:(2 + 2)) # eval-ok: build-time constant, no user input
println(_STARTUP)
