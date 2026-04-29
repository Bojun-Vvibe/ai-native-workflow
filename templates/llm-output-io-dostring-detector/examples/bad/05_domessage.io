// Evaluates a parsed message tree built from a string.
expr := System args at(1)
msg := Message fromString(expr)
Lobby doMessage(msg)
