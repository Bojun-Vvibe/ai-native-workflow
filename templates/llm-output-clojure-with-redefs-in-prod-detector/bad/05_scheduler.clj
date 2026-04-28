(ns my.app.scheduler
  "Background job runner. Runs on every node."
  (:require [my.app.clock :as clock]
            [my.app.jobs :as jobs]))

(defn run-due! []
  ;; "Pin" the clock so all jobs in this batch see the same now.
  ;; This rebinds clock/now process-globally — other threads will see it.
  (with-redefs [clock/now (constantly (clock/now))]
    (doseq [job (jobs/due)]
      (jobs/run! job))))
