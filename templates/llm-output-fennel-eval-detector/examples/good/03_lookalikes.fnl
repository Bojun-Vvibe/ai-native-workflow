;; good: lookalike identifiers that share the substring `eval`
(fn evaluate-score [x] (* x 2))
(fn re-eval [x] (+ x 1))
(local evaluator-name "v1")
(local fennel-evaluation 42)
(print (evaluate-score 3))
(print (re-eval 4))
(print evaluator-name)
(print fennel-evaluation)
