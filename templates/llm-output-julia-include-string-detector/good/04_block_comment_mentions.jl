#=
   Block comment that names every dangerous API on purpose:
       include_string(Main, body)
       eval(Meta.parse(body))
       eval(Meta.parseall(body))
       Base.invokelatest(eval, Meta.parse(body))
       include(download(url))
   None of these should trigger the detector because they live inside #= =#.
=#
function safe_dispatch(cmd::Symbol, x::Int)
    cmd === :double && return 2 * x
    cmd === :square && return x * x
    error("unknown command")
end
