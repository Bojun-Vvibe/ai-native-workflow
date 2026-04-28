-- Good: pcall feeds an `assert`, an `if`, a `return`, and an `and`/`or`
-- expression — all consume the boolean.
local cjson = require("cjson.safe")

local function strict_decode(payload)
    assert(pcall(cjson.decode, payload), "bad json")
end

local function try_decode(payload)
    if pcall(cjson.decode, payload) then
        return true
    end
    return false
end

local function fallback(payload)
    return pcall(cjson.decode, payload)
end

local function chained(payload)
    local ok = pcall(cjson.decode, payload) and true or false
    return ok
end

return { strict_decode, try_decode, fallback, chained }
