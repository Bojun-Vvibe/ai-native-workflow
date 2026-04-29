#!/usr/bin/env fish
# bad/03_dot_alias.fish — `.` is an alias for source; same risk.
set -l p /tmp/snippet.fish
. $p
