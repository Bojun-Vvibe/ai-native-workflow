;;; (compile nil FORM) compiles a form at runtime. Dangerous when FORM
;;; comes from outside.
(defun build-fn (body)
  (compile nil `(lambda (x) ,body)))

;;; load with a path from user input
(defun load-plugin (name)
  (load (format nil "/var/plugins/~A.lisp" name)))
