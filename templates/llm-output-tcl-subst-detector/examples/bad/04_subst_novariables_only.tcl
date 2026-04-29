#!/usr/bin/env tclsh
# bad/04_subst_novariables_only.tcl — -novariables disables $var
# expansion but [..] command substitution still runs.
set tmpl {[exec id]}
puts [subst -novariables $tmpl]
