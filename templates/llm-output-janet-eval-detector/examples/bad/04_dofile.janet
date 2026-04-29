# dofile loads and evaluates another Janet source file.
(defn load-plugin [name]
  (dofile (string "plugins/" name ".janet")))
