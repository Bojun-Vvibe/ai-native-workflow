-- Good: pre-compiled handlers chosen by name; no string compilation
handlers =
  greet: (n) -> "hi " .. n
  bye:   (n) -> "bye " .. n

print handlers.greet "world"
print handlers.bye "moon"
