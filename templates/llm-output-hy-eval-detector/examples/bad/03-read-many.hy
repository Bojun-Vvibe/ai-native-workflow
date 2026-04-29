; BAD: hy.read-many parses an entire program from data
(defn load-script [text]
  (for [form (hy.read-many text)]
    (hy.eval form)))
