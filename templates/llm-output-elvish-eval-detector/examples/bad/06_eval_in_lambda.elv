#!/usr/bin/env elvish
# bad/06_eval_in_lambda.elv — eval inside a lambda body `{ ... }`.
# The lambda is then bound to a key — every keypress runs eval on
# attacker data.
var run-snippet = { |code| eval $code }
$run-snippet 'echo hi'
