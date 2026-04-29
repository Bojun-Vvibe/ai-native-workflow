module Loader

# parseall handles multi-statement payloads
function load_all(blob::AbstractString)
    return Core.eval(@__MODULE__, Meta.parseall(blob))
end

end
