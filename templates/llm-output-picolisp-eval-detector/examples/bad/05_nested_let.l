# Bad: nested eval in a let binding still flags.
(de score (Form)
   (let R 0
      (setq R (eval Form))
      R ) )
