;; bad: eval inside a loop over forms parsed at runtime
(local forms (parse-all (slurp "snippets.fnl")))
(each [_ f (ipairs forms)]
    (eval f))
