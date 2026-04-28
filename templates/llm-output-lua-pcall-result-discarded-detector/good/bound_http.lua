-- Good: result is bound and inspected.
local http = require("socket.http")

local function refresh_feed(url)
    local ok, body = pcall(http.request, url)
    if not ok then
        return nil, body
    end
    return body
end

return refresh_feed
