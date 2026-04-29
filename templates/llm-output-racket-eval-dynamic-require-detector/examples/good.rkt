#lang racket
;; good.rkt — Racket patterns that look load-ish but are safe.
;; Run:  python3 detect.py examples/good.rkt   (expect 0 findings)

;; 1) dynamic-require with a quoted module-path literal — resolved
;;    at compile time, no runtime string flow.
(define jpeg-bytes->bitmap
  (dynamic-require 'racket/draw 'jpeg-bytes->bitmap))

;; 2) dynamic-require with another quoted literal — also a constant,
;;    also safe.
(define base-namespace-anchor
  (dynamic-require 'racket/base 'namespace-anchor))

;; 3) namespace-require with quoted literal.
(namespace-require 'racket/list)

;; 4) eval of a quasiquoted s-expression literal — normal
;;    metaprogramming, not string-EVAL.
(define (build-and-run x)
  (eval `(+ ,x 1) (make-base-namespace)))

;; 5) Hash-table dispatch — the idiomatic alternative to "look up a
;;    function by name and run it".
(define dispatch
  (hash 'add (lambda (a b) (+ a b))
        'sub (lambda (a b) (- a b))))

(define (apply-op op a b)
  ((hash-ref dispatch op) a b))

;; 6) syntax-parse / define-syntax — compile-time, hygienic, safe.
(define-syntax-rule (square x) (* x x))

;; 7) Mention of (eval (read ...)) inside a string literal — must
;;    not trigger.
(define warning-text
  "Never write (eval (read (open-input-string s))) in production.")

;; 8) Mention inside a `;` comment — must not trigger.
;; (eval (read (open-input-string s)) ...) is dangerous.
;; (load "foo.rkt") would run foo.rkt with full filesystem reach.

;; 9) Suppression — a sandboxed test helper that uses make-evaluator
;;    behind the scenes, justified inline.
(define (test-roundtrip lit)
  (eval (read (open-input-string lit)) (make-base-namespace))) ; eval-string-ok — fixture only
