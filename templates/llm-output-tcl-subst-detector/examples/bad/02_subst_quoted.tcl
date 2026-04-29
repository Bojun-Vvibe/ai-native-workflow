#!/usr/bin/env tclsh
# bad/02_subst_quoted.tcl — quoted-string interpolation through subst.
set header "from: alice"
set body   "hi"
puts [subst "$header\n$body"]
