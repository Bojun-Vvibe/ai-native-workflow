;;; Pure data definitions and arithmetic.
(defpackage :myapp (:use :cl))
(in-package :myapp)

(defparameter *pi-ish* 3.14159)

(defun area (r) (* *pi-ish* r r))

(defun safe-parse-int (s)
  ;; parse-integer is safe; it does NOT execute code.
  (parse-integer s :junk-allowed t))
