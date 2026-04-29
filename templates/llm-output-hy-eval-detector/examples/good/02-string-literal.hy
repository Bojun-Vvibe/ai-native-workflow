; GOOD: string literal contains the word eval but no call
(defn warn []
  (print "do not use eval or hy.eval on user input"))
