#!/usr/bin/env zsh
# good/05_lookalikes.zsh — identifiers that merely contain the
# substring "eval" (`evaluate`, `my_eval_helper`) must NOT be flagged.
# Same for `print` without `-z`, and parameter expansion flags that
# do NOT include `e` (e.g. `(L)` for lower-case, `(U)` for upper).
function evaluate_score { echo $((RANDOM)); }
my_eval_helper=$(evaluate_score)
echo $my_eval_helper
print "regular print, no -z"
upper=${(U)my_eval_helper}
lower=${(L)my_eval_helper}
echo $upper $lower
