#!/usr/bin/env zsh
# bad/02_eval_quoted.zsh — eval of a double-quoted string with $vars.
# Double quotes in shell do NOT prevent expansion; this is still eval
# of attacker-influenced data.
header="X-User: $USER"
body="$1"
eval "echo $header; echo $body"
