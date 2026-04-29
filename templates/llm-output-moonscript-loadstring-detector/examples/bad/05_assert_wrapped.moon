-- Bad: assert-wrapped loadstring still flagged on the inner call
user_expr = arg[1]
print (assert loadstring(user_expr))!
