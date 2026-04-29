#!/usr/bin/env elvish
# bad/07_eval_after_semi.elv — eval at command position after `;`.
var x = 'put hi'; eval $x
