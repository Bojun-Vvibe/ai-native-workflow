; Bad fixture: 7 instances of the (eval (read <string-port>)) anti-idiom.

; 1: classic R5RS/R7RS spelling — open-input-string + read + eval
(define (run-snippet s)
  (eval (read (open-input-string s))
        (interaction-environment)))

; 2: R6RS spelling — open-string-input-port
(define (run-snippet-r6rs s)
  (eval (read (open-string-input-port s))
        (environment '(rnrs))))

; 3: with-input-from-string thunk-style
(define (run-snippet-thunk s)
  (eval (with-input-from-string s read)
        (interaction-environment)))

; 4: call-with-input-string variant
(define (run-snippet-cwis s)
  (eval (read (call-with-input-string s)) (interaction-environment)))

; 5: SRFI-30-ish read-from-string
(define (run-snippet-rfs s)
  (eval (read-from-string s) (interaction-environment)))

; 6: hypothetical string->expression helper
(define (run-snippet-str s)
  (eval (string->expression s) (interaction-environment)))

; 7: multi-line spelling (still detected)
(eval
  (read
    (open-input-string user-input))
  (interaction-environment))
