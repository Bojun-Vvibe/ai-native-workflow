; Good fixture: same intents as bad.scm, expressed without (eval <string-derived-form>).

; 1: dynamic "variable name" -> use a hash-table keyed by symbol
(define models (make-hash-table))
(let loop ((i 0))
  (when (< i 5)
    (hash-table-set! models (string->symbol (string-append "model-" (number->string i)))
                     (fit data))
    (loop (+ i 1))))

; 2: parsing untrusted data -> read into a *form* and pattern-match it
;    as data; never (eval ...) it.
(define parsed
  (read (open-input-string "(some user supplied (sexpr 1 2 3))")))
(case (car parsed)
  ((some) (handle-some (cdr parsed)))
  (else   (error "unknown form")))

; 3: normal metaprogramming -> eval of a quoted/quasiquoted form (NOT
;    a string). The detector must NOT flag this.
(eval '(+ 1 2) (interaction-environment))
(eval `(+ ,a ,b) (interaction-environment))

; 4: a macro is the right tool for compile-time code generation
(define-syntax with-trace
  (syntax-rules ()
    ((_ name body ...)
     (begin (display "calling ") (display 'name) (newline)
            body ...))))

; 5: a comment that mentions (eval (read (open-input-string s))) must
;    not trigger:
; avoid (eval (read (open-input-string s))) — it's an injection sink

; 6: a string literal that mentions it must not trigger either:
(define warning-message
  "do not use (eval (read (open-input-string s))) in production")

; 7: read alone (without eval) returns a datum (data). On its own it's
;    harmless — and the detector must NOT flag it.
(define just-parsed (read (open-input-string "(+ 1 2)")))
(display just-parsed) ; => (+ 1 2)

; 8: an audited internal use can be suppressed inline:
(define (internal-eval s)
  (eval (read (open-input-string s)) (interaction-environment))) ; eval-string-ok: unit-test sexpr roundtrip
