#!/usr/bin/env elvish
# bad/01_eval_var.elv — bare `eval $code`. $code is attacker data.
var code = 'echo hello'
eval $code
