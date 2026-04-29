#!/bin/ksh
# `${#var}` (length) and `$#` (argc) must not be confused with the
# indirect ${!var} form. Relative paths like `./foo` must not be
# confused with the dot-include `.` builtin.
print "argc=$#"
print "len=${#PATH}"
./bin/run-tool start
