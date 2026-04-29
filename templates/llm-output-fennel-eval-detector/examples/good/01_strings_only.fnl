;; good: doc strings that mention (eval ...) inside literals
(local doc1 "Do not call (eval form) on user input.")
(local doc2 "(fennel.eval src) is dangerous in production.")
(local doc3 "(eval-compiler ...) bypasses the macro sandbox.")
(print doc1)
(print doc2)
(print doc3)
