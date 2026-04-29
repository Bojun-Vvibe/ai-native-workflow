#!/usr/bin/env tclsh
# good/04_suppressed.tcl — audited subst suppressed with marker.
set tmpl {hello world}
puts [subst $tmpl]    ;# subst-ok
puts [subst "$tmpl"]  ;# subst-ok
