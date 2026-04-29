;; good: comments mentioning the keywords are ignored
;; (eval form) would be dangerous here.
;; (fennel.eval src) is also discouraged.
;; (eval-compiler ...) is the worst form.
(local safe 1)
(print safe)
