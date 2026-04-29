; BAD: hy.eval-and-compile around runtime data
(defn macro-builder [form]
  (hy.eval-and-compile form))
