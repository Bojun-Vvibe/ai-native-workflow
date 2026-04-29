#!/usr/bin/env zsh
# good/01_eval_literal.zsh — eval of a fully literal string. No $, no
# `, no $(...). Re-parsing a constant has no injection surface; the
# detector skips it.
eval 'set -- a b c'
eval "set -o pipefail"
echo $1 $2 $3
