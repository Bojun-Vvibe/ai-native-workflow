#!/bin/ksh
# `command eval` bypasses functions but still re-parses input.
expr="$1"
command eval "$expr"
