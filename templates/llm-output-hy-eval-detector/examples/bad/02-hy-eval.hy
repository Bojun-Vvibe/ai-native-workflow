; BAD: explicit hy.eval on attacker-controlled string
(defn execute [s]
  (hy.eval (hy.read s)))
