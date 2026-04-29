-- Bad: classic Lua 5.1 loadstring with paren form
user_expr = arg[1] or "1+1"
f = loadstring("return " .. user_expr)
print f!
