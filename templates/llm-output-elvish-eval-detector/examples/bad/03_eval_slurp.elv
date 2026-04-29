#!/usr/bin/env elvish
# bad/03_eval_slurp.elv — eval of a file's contents. Path comes from
# a variable; an attacker who can write that path owns the runtime.
var path = $E:HOME/.config/myapp/init.elv
eval (slurp < $path)
