#!/bin/ksh
# `builtin eval` -- ksh-specific wrapper, same hazard.
expr="$1"
builtin eval "$expr"
