# Good: pass a function (not a string) to setTimeout / setInterval
setTimeout (-> console.log "hi"), 1000
setInterval (-> console.log "tick"), 5000
