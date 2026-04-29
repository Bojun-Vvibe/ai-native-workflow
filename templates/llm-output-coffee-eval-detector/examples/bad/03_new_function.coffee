# Bad: new Function from a string
body = process.argv[2]
fn = new Function "x", body
console.log fn(7)
