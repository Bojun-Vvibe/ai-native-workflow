# obfuscated: docstring claims it is safe, then immediately uses include_string.
"""
    safe_runner(snippet)

Runs the snippet in a sandboxed module. (It does not. The string `eval` here
is just documentation; the real call below is the dangerous one.)
"""
function safe_runner(snippet)
    return include_string(Main, snippet, "user.jl")
end
