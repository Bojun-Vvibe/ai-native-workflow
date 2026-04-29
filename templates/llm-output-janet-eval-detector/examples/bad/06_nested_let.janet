# nested inside a let -- still a sink.
(defn evaluate-config [path]
  (let [src (slurp path)]
    (eval-string src)))
