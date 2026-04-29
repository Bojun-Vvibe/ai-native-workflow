#!/usr/bin/env zsh
# bad/05_eval_after_then.zsh — eval inside an `if ... then` body.
if [[ -n $cmd ]] then; eval $cmd; fi
