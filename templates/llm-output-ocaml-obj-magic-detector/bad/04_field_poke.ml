(* 04_field_poke.ml — raw block introspection. *)
let first_field x =
  let r = Obj.repr x in
  Obj.field r 0

let mutate x v =
  let r = Obj.repr x in
  Obj.set_field r 0 (Obj.repr v)
