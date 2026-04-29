#!/usr/bin/env zsh
# bad/07_parexp_e_flag.zsh — the (e) parameter-expansion flag forces
# a SECOND eval pass on the value of the parameter. Same blast radius
# as bare eval, often missed in code review.
template='hello $(id)'
result=${(e)template}
echo $result
