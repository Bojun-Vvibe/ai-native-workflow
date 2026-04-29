#!/usr/bin/env tcsh
# good/03_in_single_quotes.tcsh — single quotes are inert in csh.
# `$x` and backticks here are literal characters, not expansions,
# so the eval invocation has no dynamic interpolation surface.
eval 'echo $x and `cmd`'
