#!/usr/bin/env elvish
# good/03_in_single_quotes.elv — single-quoted literals are inert in
# elvish. Mentioning the word `eval $foo` inside a `'...'` string is
# documentation, not code.
var msg = 'do not run: eval $foo'
var warn = 'avoid eval (slurp) on untrusted input'
echo $msg
echo $warn
