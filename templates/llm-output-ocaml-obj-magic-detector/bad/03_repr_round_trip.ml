(* 03_repr_round_trip.ml — repr/obj round-trip is just as unsafe. *)
let smuggle (x : 'a) : 'b =
  let r = Obj.repr x in
  Obj.obj r
