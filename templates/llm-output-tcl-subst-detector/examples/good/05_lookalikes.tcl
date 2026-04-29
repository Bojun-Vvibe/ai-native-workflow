#!/usr/bin/env tclsh
# good/05_lookalikes.tcl — proc/var names that contain "subst" must
# not trip the detector.
proc substring_safe {s} { return $s }
set substitutions 0
puts [substring_safe "ok"]
puts $substitutions
