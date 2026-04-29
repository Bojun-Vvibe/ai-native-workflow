-- Bad: Lua 5.2+ string-form load with concatenation
expr = arg[1]
maker = load("return function(x) return x * " .. expr .. " end")
print maker!(3)
