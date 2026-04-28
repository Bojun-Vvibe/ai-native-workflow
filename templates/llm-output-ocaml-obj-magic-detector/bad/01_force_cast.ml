(* 01_force_cast.ml — coerce a string into an int the wrong way. *)
let coerce (s : string) : int =
  Obj.magic s

let () = Printf.printf "%d\n" (coerce "hello")
