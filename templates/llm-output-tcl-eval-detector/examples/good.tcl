#!/usr/bin/env tclsh
# Good fixture: zero findings expected.
# Demonstrates the safe alternatives to `eval`.

set cmd_list [list puts "hello world"]

# Tcl 8.5+ argument expansion — preferred over `eval`:
{*}$cmd_list

# Direct command invocation:
puts "hello world"

# Building a list and invoking via a known command:
set args [list "--force" "prod"]
exec deploy {*}$args

# `eval` literally appearing inside a comment is fine:
#   eval $cmd  -- documented anti-pattern, not real code

# `eval` literally appearing inside a double-quoted string is fine:
set msg "do not call eval \$cmd in production"
puts $msg

# Suppression marker on an audited line:
set audited "puts ok"
eval $audited  ;# eval-ok: reviewed 2026-04-29, audited literal in test harness

# A proc named `evaluate` should NOT match — only the bareword `eval`:
proc evaluate {expr} { return [expr $expr] }
puts [evaluate {1 + 2}]

# A variable named `eval_log` should NOT match either:
set eval_log "trace"
puts $eval_log
