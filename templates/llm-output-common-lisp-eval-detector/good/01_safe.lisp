;;; Safe code: no eval, no read-from-string, no runtime compile.
;;; Comments and strings mention these dangerous names but should NOT trigger.

;;; This function is named eval-thing but is not (eval ...).
(defun eval-thing (x) (* x 2))

;;; A string that mentions "(eval foo)" — must not trigger.
(defparameter *doc*
  "Do not write (eval (read-from-string s)). It is unsafe.")

;;; Block comment also mentions it.
#|
   Avoid (compile nil form) on user input.
   Avoid (load path) where path is user-controlled.
|#

;;; Calling a precompiled named function — safe.
(defun greet (name) (format nil "hello ~A" name))

;;; (compile 'greet) — compiles a NAMED function ahead of time. Not flagged.
(compile 'greet)
