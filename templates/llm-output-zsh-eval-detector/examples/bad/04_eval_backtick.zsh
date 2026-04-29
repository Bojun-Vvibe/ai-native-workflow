#!/usr/bin/env zsh
# bad/04_eval_backtick.zsh — eval of a backtick command substitution.
eval `git config --get alias.$1`
