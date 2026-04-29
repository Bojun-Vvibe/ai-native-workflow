module BadOne

# LLM-generated handler that takes a user-supplied snippet and runs it.
function run_user_code(snippet::AbstractString)
    return include_string(@__MODULE__, snippet)
end

end # module
