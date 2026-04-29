#!/usr/bin/env tclsh
# bad/03_subst_nobackslashes_only.tcl — only -nobackslashes set;
# command substitution `[..]` is still active.
set tmpl {hi [exec id]}
puts [subst -nobackslashes $tmpl]
