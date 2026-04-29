-- Bad: MoonScript implicit-call form, no parens
expr = arg[1] or "1"
fn = loadstring "return #{expr}"
print fn!
