-- Good: long-bracket comments and strings mentioning pcall must not
-- be flagged. There are no actual pcall calls executed in this file.

--[==[
    Historical note: we used to write
        pcall(foo)
    here and the errors vanished. Now we always bind:
        local ok, err = pcall(foo)
]==]

local sample = [[
   pcall(http.request, "http://example")
   pcall(json.decode, "{}")
]]

local sample2 = [==[
   xpcall(handler, on_err)
]==]

return sample .. sample2
