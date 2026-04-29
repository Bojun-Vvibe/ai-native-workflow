#!/usr/bin/env fish
# bad/04_source_dq_interp.fish — double-quoted path with $var
# interpolation. fish DOES interpolate inside "...".
set -l name plugin
source "$HOME/.config/fish/$name.fish"
