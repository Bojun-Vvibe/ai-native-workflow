# direct eval of a parsed user form -- classic eval sink.
(defn run-user-form [src]
  (eval (parse src)))
