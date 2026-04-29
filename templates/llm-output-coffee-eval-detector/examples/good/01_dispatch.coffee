# Good: dispatch object replaces eval entirely
ops =
  double: (x) -> x * 2
  square: (x) -> x * x
  negate: (x) -> -x

userOp = process.argv[2] or "double"
fn = ops[userOp]
if fn?
  console.log fn(7)
else
  throw new Error "unknown op: #{userOp}"
