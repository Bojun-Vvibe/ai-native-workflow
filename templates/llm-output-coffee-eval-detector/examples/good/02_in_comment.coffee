# Good: mention of eval in a comment must not trigger.
# We deliberately do not call eval here. Function("x") in a comment
# is also fine. Even setTimeout "x", 1 inside a comment is fine.
console.log "no dynamic eval here"
