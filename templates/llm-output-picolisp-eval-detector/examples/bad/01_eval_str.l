# Bad: classic eval over a parsed user string.
(de handle-cmd (Input)
   (eval (str Input)) )
