// Idiomatic F#: discriminated union + pattern match.
// No reflection. Must NOT be flagged. Comments mentioning
// GetMethod or InvokeMember are inside `//` line comments and
// must be ignored.
module SafeDispatch

type Op =
    | Add of int * int
    | Sub of int * int
    | Mul of int * int

let dispatch op =
    match op with
    | Add (a, b) -> a + b
    | Sub (a, b) -> a - b
    | Mul (a, b) -> a * b
