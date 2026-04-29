#!/usr/bin/env zsh
# bad/08_eval_after_pipe.zsh — eval at command position after `|`.
# Common in "build a command, pipe through eval" idioms.
get_cmd | eval "$(cat)"
