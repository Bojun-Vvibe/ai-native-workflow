(* 05_unsafe_array.ml — bypassing the type-checker for "speed". *)
let fast_get (a : 'a array) (i : int) : 'b =
  Obj.magic (Obj.unsafe_get (Obj.repr a) i)
