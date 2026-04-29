;; bad: older string variant
(local src (read-config "rules.fnl"))
(fennel.eval-string src)
