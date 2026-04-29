#!/usr/bin/env tclsh
# good/01_safe_flags.tcl — both -nocommands set: command substitution
# is disabled. Variable expansion may or may not be allowed; either
# way, this is no longer an exec sink.
set tmpl {hi $name}
set name "alice"
puts [subst -nocommands $tmpl]
puts [subst -nocommands -novariables $tmpl]
puts [subst -nocommands -novariables -nobackslashes $tmpl]
