-- Good: dispatch table replaces loadstring entirely
ops =
  double: (x) -> x * 2
  square: (x) -> x * x
  negate: (x) -> -x

user_op = arg[1] or "double"
fn = ops[user_op]
if fn
  print fn 7
else
  error "unknown op: #{user_op}"
