# Bad: setTimeout with a string first arg => implicit eval
setTimeout "console.log('hi')", 1000
