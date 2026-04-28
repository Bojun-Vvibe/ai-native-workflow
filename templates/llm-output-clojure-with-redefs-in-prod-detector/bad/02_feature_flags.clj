(ns my.app.feature-flags
  (:require [my.app.config :as cfg]))

(defn with-flag-on [flag thunk]
  (with-redefs-fn {#'cfg/enabled? (constantly true)}
    thunk))

(defn render-page [req]
  (with-flag-on :new-ui
    (fn [] (str "<html>" (:user req) "</html>"))))
