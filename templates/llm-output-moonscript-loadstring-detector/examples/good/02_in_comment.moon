-- Good: mention of loadstring inside a comment must not trigger.
-- We deliberately do not call loadstring here; see dispatch table.
-- Also: load("x") in a comment is fine.
print "no dynamic eval here"
