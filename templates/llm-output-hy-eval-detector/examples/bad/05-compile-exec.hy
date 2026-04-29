; BAD: compile(... "exec") then exec
(defn rebuild [src]
  (setv co (compile src "<live>" "exec"))
  (exec co))
