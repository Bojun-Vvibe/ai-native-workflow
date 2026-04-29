# symbols whose names contain "eval" but are NOT eval -- not flagged.
(defn evaluate-score [hand] (length hand))
(defn re-evaluate [x] (* x 2))
(def evaluator-name "scorer")
(print (evaluate-score [1 2 3]))
