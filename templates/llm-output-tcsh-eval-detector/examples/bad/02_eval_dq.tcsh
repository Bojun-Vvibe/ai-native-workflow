#!/usr/bin/env tcsh
# bad/02_eval_dq.tcsh — double-quoted string with $var interpolation.
set name = "world"
eval "echo hello $name"
