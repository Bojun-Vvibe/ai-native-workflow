#!/usr/bin/env tclsh
# good/02_in_comment.tcl — `subst $x` inside a comment must not be flagged.
# example: subst $x ;# do not do this
# also: [subst $tmpl]
puts ok
