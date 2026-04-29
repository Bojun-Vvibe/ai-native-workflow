// Pure object construction. No eval.
Point := Object clone do(
  x := 0
  y := 0
  distanceTo := method(other,
    ((x - other x) squared + (y - other y) squared) sqrt
  )
)
p := Point clone
p x = 3
p y = 4
writeln(p distanceTo(Point clone))
