# Bad: setInterval with a string first arg => implicit eval, paren form
setInterval("doWork()", 5000)
