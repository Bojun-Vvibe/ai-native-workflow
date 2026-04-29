#!/usr/bin/env elvish
# bad/05_eval_after_pipe.elv — eval at command position after `|`.
echo $user-supplied-script | eval (slurp)
