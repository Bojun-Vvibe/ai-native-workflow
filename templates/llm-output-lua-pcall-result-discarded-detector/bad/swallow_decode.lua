-- Bad: xpcall used the same way — error handler runs but caller
-- still cannot tell whether the operation succeeded.
local cjson = require("cjson.safe")

local function maybe_decode(payload)
    xpcall(cjson.decode, function(e) end, payload)
end

local function batch(payloads)
    for _, p in ipairs(payloads) do
        pcall(maybe_decode, p) ; pcall(print, p)
    end
end

return batch
