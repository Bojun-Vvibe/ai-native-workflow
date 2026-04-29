#!/usr/bin/env zsh
# good/03_in_single_quotes.zsh — single-quoted literals are inert in
# zsh: no expansion happens. Mentioning the word "eval $foo" inside
# a `'...'` string is documentation, not code.
msg='do not run: eval $foo'
warn='avoid print -z $cmd in widgets'
echo $msg
echo $warn
