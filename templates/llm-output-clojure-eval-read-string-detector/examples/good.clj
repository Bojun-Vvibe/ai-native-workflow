;; Good fixture: same intents as bad.clj, expressed without (eval (read-string ...)).

;; 1: dynamic "var name" -> use a map keyed by keyword (the idiomatic answer)
(def models
  (into {}
        (for [i (range 5)]
          [(keyword (str "model-" i)) (fit data)])))

;; 2: dynamic column reference -> just use get / keyword lookup
(defn get-value [name]
  (get row (keyword name)))

;; 3: parsing untrusted input -> use clojure.edn/read-string (data only,
;;    no code evaluation). The detector must NOT flag this.
(require '[clojure.edn :as edn])
(def config (edn/read-string (slurp "config.edn")))

;; 4: read-string alone (without eval) returns a form (data). On its own
;;    it's harmless — and the detector must NOT flag it.
(def parsed-form (read-string "(+ 1 2)"))
(println parsed-form) ; => (+ 1 2)

;; 5: normal metaprogramming — eval of a quoted/syntax-quoted form
;;    (NOT a string). The detector must NOT flag this.
(eval '(+ 1 2))
(eval `(+ ~a ~b))

;; 6: a macro is the right tool for compile-time code generation
(defmacro defn-traced [name args & body]
  `(defn ~name ~args
     (println "calling" '~name)
     ~@body))

;; 7: a comment that mentions (eval (read-string ...)) must not trigger:
;; avoid (eval (read-string s)) — it's an injection sink

;; 8: a string literal that mentions it must not trigger either:
(def warning-message "do not use (eval (read-string s)) in production")

;; 9: a regex literal that mentions it must not trigger either:
(def pattern #"(eval (read-string \"x\"))")

;; 10: an audited internal use can be suppressed inline:
(defn internal-eval [s]
  (eval (read-string s))) ;; eval-read-string-ok: REPL-helper macro, internal-only
