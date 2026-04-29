#lang racket
;; bad.rkt — every dynamic-load anti-pattern the detector should catch.
;; Run:  python3 detect.py examples/bad.rkt

;; bad-1: classic string-EVAL via open-input-string
(define (run-snippet s)
  (eval (read (open-input-string s))
        (make-base-namespace)))

;; bad-2: R6RS-style spelling
(define (run-snippet-r6 s)
  (eval (read (open-string-input-port s))
        (make-base-namespace)))

;; bad-3: with-input-from-string
(define (run-snippet-wifs s)
  (eval (with-input-from-string s read)
        (current-namespace)))

;; bad-4: call-with-input-string spelling
(define (run-snippet-cwis s)
  (eval (read (call-with-input-string s)) (current-namespace)))

;; bad-5: read-from-string SRFI-style
(define (run-snippet-rfs s)
  (eval (read-from-string s) (current-namespace)))

;; bad-6: eval-syntax with reconstructed syntax
(define (run-syntax form)
  (eval-syntax (datum->syntax #f form) (current-namespace)))

;; bad-7: dynamic-require with computed module path
(define (load-plugin user-path)
  (dynamic-require (string->path user-path) 'main))

;; bad-8: dynamic-require-for-syntax (always flagged)
(define (compile-time-load mod)
  (dynamic-require-for-syntax mod 'expand))

;; bad-9: namespace-require with quasi-built spec
(define (require-by-name mod-sym)
  (namespace-require `(file ,(symbol->string mod-sym))))

;; bad-10: legacy load — runs file in current namespace
(define (run-file path)
  (load path))

;; bad-11: load/use-compiled — same risk plus ZO cache
(define (run-file-compiled path)
  (load/use-compiled path))
