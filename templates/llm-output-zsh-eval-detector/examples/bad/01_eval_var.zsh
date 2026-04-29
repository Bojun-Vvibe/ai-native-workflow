#!/usr/bin/env zsh
# bad/01_eval_var.zsh — bare `eval $cmd`. $cmd is attacker-controlled.
cmd="ls /tmp"
eval $cmd
