#!/usr/bin/env tcsh
# good/01_eval_literal.tcsh — fully literal: no $, no backtick, no !.
# Constant string = no injection surface; detector skips it.
eval 'echo hello world'
eval echo static
