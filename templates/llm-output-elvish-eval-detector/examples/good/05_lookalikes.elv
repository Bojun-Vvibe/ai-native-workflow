#!/usr/bin/env elvish
# good/05_lookalikes.elv — identifiers that merely contain the
# substring "eval" (`evaluate`, `my-eval-helper`, `eval-result`)
# must NOT be flagged. Same for `re:` regex match functions and
# normal external commands.
fn evaluate-score { put (* (randint 0 100) 1) }
var my-eval-helper = (evaluate-score)
var eval-result = $my-eval-helper
echo $eval-result
re:match '\beval\b' 'this string mentions eval'
