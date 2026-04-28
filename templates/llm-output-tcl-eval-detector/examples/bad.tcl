#!/usr/bin/env tclsh
# Bad fixture: multiple `eval STRING` calls that should each be flagged.

set cmd "puts hello"
eval $cmd                                  ;# 1: variable into eval

set action [lindex $argv 0]
eval "$action"                             ;# 2: quoted variable into eval

set result [eval [list puts $action]]     ;# 3: command-substitution into eval
puts $result

proc run_for {target} {
    eval "deploy_$target --force"          ;# 4: interpolated string into eval
}
run_for prod

# Even braced-literal eval gets flagged — `eval` itself is the smell:
eval {puts "hello world"}                  ;# 5: braced-literal eval

# Inside an if/else body, command position after `then`/`else`:
if {$cmd ne ""} then { eval $cmd }         ;# 6: after `then`
if {$cmd eq ""} { puts no } else { eval $cmd }  ;# 7: after `else`

# After a `;` separator on the same line:
set x 1; eval $cmd                         ;# 8: after `;`
