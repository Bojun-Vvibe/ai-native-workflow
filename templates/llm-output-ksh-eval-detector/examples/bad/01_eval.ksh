#!/bin/ksh
# Bareword eval re-parses its argument as shell input.
user_cmd="$1"
eval "$user_cmd"
