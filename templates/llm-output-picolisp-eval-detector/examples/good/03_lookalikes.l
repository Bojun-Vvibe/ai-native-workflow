# Good: lookalike symbol names that contain "eval", "run", "load"
# but are NOT the built-ins.
(de evaluate-score (X) (* X 2))
(de runner-state () 'idle)
(de loaded? (X) (assoc X *Cache))
(setq *Stats (list (evaluate-score 7) (runner-state)))
