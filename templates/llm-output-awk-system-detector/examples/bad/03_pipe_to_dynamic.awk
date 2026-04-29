#!/usr/bin/awk -f
# Pipes data into a shell command built from input.
{ print $0 | ("mailx -s subject " $3) }
