REBOL [Title: "bad-load-then-do"]

; load + do composition: parse a string into a block, then evaluate.
do load "print [1 2 3]"

; do to-block — same hazard.
do to-block user-input

; bare load on a string literal — almost always followed by do.
config: load "rule: 'allow"
