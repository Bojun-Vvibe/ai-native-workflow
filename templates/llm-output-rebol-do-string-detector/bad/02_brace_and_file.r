REBOL [Title: "bad-do-brace-and-file"]

; Multi-line braced string passed to `do` — same risk as do "...".
do {
    print "hello"
    print "from a code blob"
}

; Loading and executing a script file whose path may be user-controlled.
do %plugins/extra.r
