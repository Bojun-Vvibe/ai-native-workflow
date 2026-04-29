;; Bad fixture: 8 instances of the (eval (read-string ...)) anti-idiom in Clojure.

;; 1: classic dynamic def via string concatenation
(doseq [i (range 5)]
  (eval (read-string (str "(def model-" i " (fit data))"))))

;; 2: dynamic form via str — column-name interpolation (injection sink)
(defn get-value [name]
  (eval (read-string (str "(:" name " row)"))))

;; 3: fully qualified clojure.core/eval — still the same anti-idiom
(clojure.core/eval (read-string "(+ 1 1)"))

;; 4: fully qualified clojure.core/read-string
(eval (clojure.core/read-string "(println :hi)"))

;; 5: load-string is the one-shot string-eval primitive
(load-string "(def x 42)")

;; 6: fully qualified load-string
(clojure.core/load-string "(def y 99)")

;; 7: multi-line spelling (still detected)
(eval
  (read-string
    (str "(def z " 1 " + " 2 ")")))

;; 8: load-string fed from a function arg (worst case)
(defn run-user-snippet [s]
  (load-string s))
