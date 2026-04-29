# comment-only mentions of (eval ...) and (dofile ...) -- ignored.
# TODO: replace the old (eval form) hot-reload path with a static
# dispatch table so we never need (dofile path) again.
(defn add [a b] (+ a b))
(print (add 2 3))
