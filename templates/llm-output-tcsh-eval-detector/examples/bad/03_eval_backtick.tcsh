#!/usr/bin/env tcsh
# bad/03_eval_backtick.tcsh — backtick command substitution feeds eval.
eval `cat /tmp/cmds.txt`
