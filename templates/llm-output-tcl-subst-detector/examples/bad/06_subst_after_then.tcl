#!/usr/bin/env tclsh
# bad/06_subst_after_then.tcl — after `then` keyword, command position.
set cond 1
set tmpl {[exec id]}
if {$cond} then { puts [subst $tmpl] }
