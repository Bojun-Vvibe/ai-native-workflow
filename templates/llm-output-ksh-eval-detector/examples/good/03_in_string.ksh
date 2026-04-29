#!/bin/ksh
# `eval`, `source`, and `${!x}` mentioned inside string literals
# must not flag.
print 'eval "$x"'
print "source ./helper.ksh"
print 'indirect form: ${!varname}'
