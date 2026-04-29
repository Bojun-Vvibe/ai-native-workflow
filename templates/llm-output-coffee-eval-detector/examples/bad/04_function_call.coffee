# Bad: Function(...) without ``new`` is the same sink
body = process.argv[2]
fn = Function("x", "return " + body)
console.log fn(2)
