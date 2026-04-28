(ns my.app.payments
  "Production payment handler with proper seams."
  (:require [my.app.gateway :as gw]))

;; Inject the gateway as an argument instead of redefining a Var.
(defn charge! [gateway order]
  (gw/post gateway order))

;; Or use a protocol so swapping implementations is explicit.
(defprotocol PaymentBackend
  (-charge [this order]))

(defrecord StripeBackend [client]
  PaymentBackend
  (-charge [_ order] (gw/post client order)))

(defn process! [backend order]
  (-charge backend order))
