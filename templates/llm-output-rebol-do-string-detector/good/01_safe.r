REBOL [Title: "good-safe"]

; Safe code: no string-eval, no load-from-string, no do %file.
; Comments and strings mention these names but should NOT trigger.

; This is a comment that says: do "print 1" is dangerous.

doc: {
    Avoid `do "..."`, `do {...}`, and `do %file.r` on untrusted input.
    Avoid `do load "..."` and `do to-block "..."` too.
}

; Words like redo and do-thing must NOT trigger.
redo: func [x] [x + 1]
do-thing: func [x] [x * 2]
print redo 5
print do-thing 5

; A normal data block — `do` here is part of a string, not code.
note: "Do not call do on user input"
print note
