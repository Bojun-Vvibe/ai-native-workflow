#!/bin/ksh
# Dot-include of a path that came from outside is arbitrary code.
plugin_path="$1"
. "$plugin_path"
