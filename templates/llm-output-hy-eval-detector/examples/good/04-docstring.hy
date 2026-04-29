; GOOD: triple-quoted docstring mentions eval
(defn safe-run [x]
  """This function does NOT (eval x) — it uses pattern matching."""
  (cond [(= x "ping") "pong"]
        [True "unknown"]))
