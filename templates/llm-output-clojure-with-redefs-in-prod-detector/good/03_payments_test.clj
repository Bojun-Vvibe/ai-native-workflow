(ns my.app.payments-test
  "Unit tests — with-redefs is appropriate here."
  (:require [clojure.test :refer [deftest is testing]]
            [my.app.payments :as p]
            [my.app.gateway :as gw]))

(deftest charge-test
  (testing "charges the gateway"
    (with-redefs [gw/post (fn [_] {:status :ok})]
      (is (= {:status :ok} (p/charge! {:amount 100}))))))

(deftest charge-failure-test
  (with-redefs-fn {#'gw/post (fn [_] (throw (ex-info "boom" {})))}
    #(is (thrown? Exception (p/charge! {:amount 1})))))
