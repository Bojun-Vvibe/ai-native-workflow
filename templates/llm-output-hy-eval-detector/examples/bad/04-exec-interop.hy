; BAD: Python interop exec with constructed source
(import sys)
(defn dyn [body]
  (exec (+ "def f():\n  " body)))
