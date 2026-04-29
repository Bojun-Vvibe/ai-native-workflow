#!/bin/ksh
# `eval` and `source` mentioned only in comments must not flag.
# eval "$x" -- this is a comment, not code
# source ./helper.ksh -- also a comment
print "hello"
