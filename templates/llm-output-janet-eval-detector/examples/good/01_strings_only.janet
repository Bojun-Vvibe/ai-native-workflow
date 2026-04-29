# the substring "(eval " appears only inside string literals and
# documentation -- never as a real form. Should NOT be flagged.
(def doc "Use (eval form) to compile and run a Janet form at runtime.")
(def example `the call (eval-string "...") returns the last value`)
(print doc)
(print example)
