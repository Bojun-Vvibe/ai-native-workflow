#!/usr/bin/env tclsh
# good/03_in_string.tcl — `subst $x` lives inside a "..." string and
# is not the keyword token at command position.
set msg "remember: subst \$x is unsafe by default"
puts $msg
