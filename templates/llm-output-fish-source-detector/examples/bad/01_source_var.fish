#!/usr/bin/env fish
# bad/01_source_var.fish — bare `source $path`. $path is attacker data.
set -l path /tmp/x.fish
source $path
