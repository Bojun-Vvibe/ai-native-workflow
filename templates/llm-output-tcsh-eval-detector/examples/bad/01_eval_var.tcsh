#!/usr/bin/env tcsh
# bad/01_eval_var.tcsh — bare `eval $cmd`. $cmd is attacker data.
set cmd = "echo hi"
eval $cmd
