#!/usr/bin/env elvish
# good/01_eval_literal.elv — eval of a fully literal double-quoted
# string. No $, no `, no (. Re-parsing a constant has no injection
# surface; the detector skips it.
eval "set-env FOO bar"
eval 'put hello'
echo done
