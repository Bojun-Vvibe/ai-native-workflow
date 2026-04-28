-- Bad: pcall result discarded as a bare statement.
-- The HTTP error vanishes and the caller has no way to know.
local http = require("socket.http")

local function refresh_feed(url)
    pcall(http.request, url)
    return "ok"
end

return refresh_feed
