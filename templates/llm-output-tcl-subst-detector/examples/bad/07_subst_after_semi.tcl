#!/usr/bin/env tclsh
# bad/07_subst_after_semicolon.tcl — after `;`, command position.
set x 1; puts [subst $x]
