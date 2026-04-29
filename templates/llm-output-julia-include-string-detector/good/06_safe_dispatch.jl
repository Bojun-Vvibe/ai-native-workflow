using JSON3

# Safe alternative: parse data, dispatch on a known set of operations.
function handle(payload::String)
    msg = JSON3.read(payload)
    op = String(msg.op)
    if op == "ping"
        return "pong"
    elseif op == "echo"
        return String(msg.value)
    else
        return "unknown"
    end
end
