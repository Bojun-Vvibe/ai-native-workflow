;; bad: nested let with eval on the bound value
(let [form (build-form payload)]
    (eval form))
