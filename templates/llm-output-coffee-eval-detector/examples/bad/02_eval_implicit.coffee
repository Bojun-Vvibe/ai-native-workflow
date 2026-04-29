# Bad: CoffeeScript implicit-call eval
expr = process.argv[2]
out = eval expr
console.log out
