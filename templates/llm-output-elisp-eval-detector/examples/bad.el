;;; bad.el --- positive fixtures for elisp-eval-detector  -*- lexical-binding: t; -*-

;; 1: bareword (eval ...) on user-supplied form
(eval user-form)

;; 2: (eval (read STRING)) — full code-injection sink
(eval (read user-supplied-string))

;; 3: (eval (car (read-from-string s))) — same sink, wrapped
(eval (car (read-from-string config-string)))

;; 4: eval-region of an attacker-controlled buffer range
(eval-region (point-min) (point-max))

;; 5: eval-buffer of a fetched-from-network temp buffer
(with-temp-buffer
  (insert (url-retrieve-synchronously remote-url))
  (eval-buffer))

;; 6: eval-string (Emacs 29+)
(eval-string config-snippet)

;; 7: eval-expression on dynamic input
(eval-expression dynamic-form)

;; 8: eval-defun in batch mode
(eval-defun nil)
