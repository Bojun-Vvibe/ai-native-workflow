; GOOD: a function NAMED evaluator but no eval/exec/compile
(defn evaluator-step [state]
  (assoc state "step" (inc (get state "step"))))
