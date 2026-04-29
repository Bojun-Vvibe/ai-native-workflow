REBOL [Title: "good-pure"]

; Pure data + arithmetic.
pi-ish: 3.14159
area: func [r] [pi-ish * r * r]
print area 10

; Calling do on a BLOCK literal (already parsed code) is the normal,
; safe usage pattern in Rebol — no string eval involved.
do [print "block literal — safe"]
