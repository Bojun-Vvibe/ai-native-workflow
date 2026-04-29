;; bad: eval applied to a runtime-built form
(local form (read-form (io.read)))
(eval form)
