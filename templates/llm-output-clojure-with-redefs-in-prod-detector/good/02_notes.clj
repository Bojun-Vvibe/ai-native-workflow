(ns my.app.notes
  "Helpers that talk about with-redefs but never call it.")

;; This namespace documents why we banned with-redefs in prod paths.
;; The string "with-redefs" appears in docstrings and comments only.

(def policy
  "We do not use `with-redefs` outside test code.
   See docs/with-redefs.md for the rationale.")

;; The form (with-redefs [...] ...) belongs in tests, never here.
;; #_ (with-redefs [foo bar] (foo))   ;; intentionally discarded sample

(defn doc-string-only []
  "Return the policy string."
  policy)
