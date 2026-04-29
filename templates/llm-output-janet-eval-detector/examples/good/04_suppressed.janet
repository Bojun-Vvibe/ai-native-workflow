# vetted boot-time eval of a constant form audited in code review.
# Suppressed with the eval-ok marker on the same line.
(eval '(do (def boot-time-marker true) nil))  # eval-ok
