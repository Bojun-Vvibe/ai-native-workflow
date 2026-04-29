#!/usr/bin/env fish
# bad/08_source_concat.fish — concatenated string with $var. fish
# concatenation is implicit; the literal segment plus $var still
# produces a dynamic path.
source /etc/myapp/$profile.fish
