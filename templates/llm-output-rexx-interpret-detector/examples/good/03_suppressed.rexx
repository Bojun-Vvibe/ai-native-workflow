/* 03_suppressed.rexx
   Demonstrates the suppression marker for a vetted, hard-coded
   trampoline. Reviewer must verify the input is not user-tainted. */
trampoline = 'say 42'
interpret trampoline /* interpret-ok */
exit 0
