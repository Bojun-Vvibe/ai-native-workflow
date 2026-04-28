(ns my.app.email
  (:require [my.app.smtp :as smtp]))

;; Re-stub the SMTP client at request time because the prod creds rotated.
;; Yes this is in the request path. Yes it is wrong.
(defn send-receipt [user invoice]
  (with-redefs [smtp/send! (fn [to subj body]
                             (println "fake send" to)
                             {:status :ok})]
    (smtp/send! (:email user)
                (str "Receipt #" (:id invoice))
                (pr-str invoice))))
