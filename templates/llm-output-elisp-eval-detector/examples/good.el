;;; good.el --- true negatives for elisp-eval-detector  -*- lexical-binding: t; -*-

;; 1: a function NAMED `evaluate-expression` is not flagged.
(defun evaluate-expression (e)
  "Pretty-print E as an arithmetic expression."
  (format "%s" e))

;; 2: `eval` mentioned in a docstring / string literal is masked.
(defun describe-eval ()
  "This function does NOT call eval; the word eval here is just text."
  "eval is mentioned but inside a string literal — safe.")

;; 3: comments are masked.
;; (eval danger) — this is in a comment, must NOT be flagged

;; 4: `funcall` is not in scope; calling a function value is fine.
(funcall my-callback arg)

;; 5: `apply` of a function value is fine.
(apply #'+ 1 2 (list 3 4))

;; 6: `(read ...)` alone (no surrounding eval) is just a parser call.
(let ((form (read user-string)))
  ;; we then dispatch on (car form) against a known whitelist
  (pcase (car form)
    ('greet (message "hi"))
    ('count (length form))))

;; 7: `(load FILE)` is out of scope for this detector.
(load "~/.emacs.d/site-lisp/known-good.el")

;; 8: audited line, suppressed by trailing comment.
(eval audited-constant-form) ; eval-ok — reviewed 2026-04-15
