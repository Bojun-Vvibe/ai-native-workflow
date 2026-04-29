#!/usr/bin/awk -f
# Concatenates a field directly into a shell command.
{ system("rm -rf " $1) }
