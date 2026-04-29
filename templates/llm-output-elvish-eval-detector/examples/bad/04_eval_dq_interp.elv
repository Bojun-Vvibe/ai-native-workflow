#!/usr/bin/env elvish
# bad/04_eval_dq_interp.elv — eval of a double-quoted string that
# contains a $variable. After eval re-parses the string, the $var
# becomes a real expansion in the second pass.
var header = 'X-User'
eval "echo "$header
