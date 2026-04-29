#!/usr/bin/env tclsh
# bad/05_subst_braced_literal.tcl — braced literal still goes through
# subst; if the literal contains `[..]` it executes. Audit explicitly.
puts [subst {hello [clock seconds]}]
