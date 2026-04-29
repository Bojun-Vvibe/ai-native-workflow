;;; LLM-style "tiny REPL": classic eval+read-from-string code injection.
(defun run-user-code (s)
  (eval (read-from-string s)))
