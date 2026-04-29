;; bad: library entry point with a runtime string
(local src (slurp "user-hook.fnl"))
(fennel.eval src)
