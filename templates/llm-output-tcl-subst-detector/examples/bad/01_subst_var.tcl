#!/usr/bin/env tclsh
# bad/01_subst_var.tcl — bare `subst $var`. Default flags allow [..]
# command substitution: an attacker who controls $tmpl gets exec.
set tmpl {hello [exec id]}
puts [subst $tmpl]
