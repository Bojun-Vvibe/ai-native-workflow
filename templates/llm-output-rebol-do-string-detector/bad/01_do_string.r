REBOL [Title: "bad-do-string"]

; LLM-style "tiny REPL" — evaluates a literal string of code.
do "print 1 + 1"

; Evaluating user input directly.
user-code: "delete %important.txt"
do user-code
