-- Good: mention of load(" inside a string literal must not trigger
doc = "Avoid load('...') and loadstring('...') for user input."
print doc
warn = "do not call loadstring on tainted data"
print warn
