#!/usr/bin/env zsh
# good/02_in_comment.zsh — eval / print -z / ${(e)x} mentioned only
# inside comments. Must NOT be flagged.
# example: do not write `eval $cmd` here
# also avoid: print -z $suggested
# nor:        ${(e)template}
echo ok
