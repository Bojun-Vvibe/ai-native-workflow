# Good: mentions of (eval ...) and (load ...) only appear in comments.
# This module deliberately avoids (eval x) and (load Path).
# We use a small dispatcher table instead, defined below.
(de dispatch (Op Args)
   (case Op
      (add (apply + Args))
      (mul (apply * Args)) ) )
