# eval inside a callback closure -- classic injection sink for any
# event handler that gets data from the network.
(defn on-message [msg]
  (def form (parse (msg :body)))
  (eval form))
