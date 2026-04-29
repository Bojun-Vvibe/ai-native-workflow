; GOOD: comment mentions eval, no actual call
; "Note: don't use (eval x) here — we use a dispatch table."
(defn dispatch [name args]
  (let [handlers {"add" + "sub" -}]
    ((get handlers name) #* args)))
