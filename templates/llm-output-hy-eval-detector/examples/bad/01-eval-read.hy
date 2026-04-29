; BAD: runtime eval of user-derived form
(defn run-user [code]
  (eval (hy.read code)))
