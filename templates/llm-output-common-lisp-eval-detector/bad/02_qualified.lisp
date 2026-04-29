;;; Package-qualified eval — same risk, different spelling.
(defun apply-rule (form)
  (cl:eval form))

;;; Common-lisp-prefixed read-from-string for "config".
(defparameter *config*
  (common-lisp:read-from-string (uiop:read-file-string "/tmp/cfg.lisp")))
