#!/bin/ksh
# Indirect name-reference expansion ${!FOO} dereferences a *name*
# stored in FOO, which is the same hazard as eval over a variable
# name.
varname="$1"
print "${!varname}"
