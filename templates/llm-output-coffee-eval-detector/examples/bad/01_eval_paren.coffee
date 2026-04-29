# Bad: classic eval with paren form
userExpr = process.argv[2] or "1+1"
result = eval("(" + userExpr + ")")
console.log result
