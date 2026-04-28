#!/usr/bin/env lua
-- Good fixture: same intents as bad.lua, expressed without dynamic-code execution.

local user_op = arg[1] or "double"

-- Dispatch table instead of loadstring:
local ops = {
    double = function(x) return x * 2 end,
    square = function(x) return x * x end,
    negate = function(x) return -x end,
}

local fn = ops[user_op]
if fn then
    print(fn(7))
else
    error("unknown op: " .. tostring(user_op))
end

-- Pre-compiled functions chosen by name, no string compilation:
local handlers = { greet = function(n) return "hi " .. n end }
print(handlers.greet("world"))

-- Mention of "loadstring" inside a comment must not trigger:
-- We deliberately do not use loadstring here; see dispatch table above.

-- Mention of "load(" inside a string literal must not trigger:
local doc = "Avoid load('...') and loadstring('...') for user input."
print(doc)

-- Long-bracket string containing the word load must not trigger:
local long = [[example: load("x") is unsafe — see README]]
print(long)

-- An intentional, audited dynamic eval can be suppressed inline:
local audited = loadstring("return 1 + 1") -- loadstring-ok: build-time constant
print(audited())
