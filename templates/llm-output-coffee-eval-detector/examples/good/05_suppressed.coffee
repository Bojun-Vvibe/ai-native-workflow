# Good: an audited build-time constant eval, suppressed inline
audited = eval("1 + 1") # eval-ok: build-time constant
console.log audited
