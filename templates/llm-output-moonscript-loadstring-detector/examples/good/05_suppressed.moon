-- Good: an audited build-time constant eval, suppressed inline
audited = loadstring "return 1 + 1" -- loadstring-ok: build-time constant
print audited!
