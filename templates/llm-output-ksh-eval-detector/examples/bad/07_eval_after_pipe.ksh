#!/bin/ksh
# Multi-pipe form: eval after a pipe still re-parses input.
get_command | eval cat
expr="$1"; eval "$expr"
