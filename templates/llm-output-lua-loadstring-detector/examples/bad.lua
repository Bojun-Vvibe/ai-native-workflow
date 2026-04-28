#!/usr/bin/env lua
-- Bad fixture: 5+ instances of dynamic-code execution that should each be flagged.

local user_expr = arg[1] or "1+1"

-- 1: classic Lua 5.1 loadstring
local f1 = loadstring("return " .. user_expr)
print(f1())

-- 2: Lua 5.2+ string-form load
local f2 = load("return " .. user_expr)
print(f2())

-- 3: assert-wrapped loadstring
print(assert(loadstring(user_expr))())

-- 4: load via concatenation of a template
local tmpl = "return function(x) return x * " .. user_expr .. " end"
local maker = load(tmpl)
print(maker()(3))

-- 5: bound-method dostring (LuaSocket / LuaJIT bindings)
local sandbox = require("sandbox")
sandbox:dostring("return os.time()")

-- 6: load wrapped in pcall
local ok, fn = pcall(load, user_expr)
if ok and fn then fn() end

-- 7: assignment with load on RHS, after `=`
local g = load(user_expr)
if g then g() end
