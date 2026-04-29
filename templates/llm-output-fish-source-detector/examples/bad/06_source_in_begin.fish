#!/usr/bin/env fish
# bad/06_source_in_begin.fish — source inside a begin/end block, after
# the `begin` keyword. Still command position, still dynamic.
begin
    set -l f $argv[1]
    source $f
end
