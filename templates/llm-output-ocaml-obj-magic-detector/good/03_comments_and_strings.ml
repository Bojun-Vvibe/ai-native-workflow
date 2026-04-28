(* 03_comments_and_strings.ml — references only inside non-code. *)

(* Historical note: Obj.magic was once recommended for fast casts,
   but it bypasses the type system entirely. Do not use Obj.repr or
   Obj.unsafe_get either. *)

let warning = "Never call Obj.magic on user input."
let tip = "Avoid Obj.repr / Obj.obj round-trips."

let () =
  print_endline warning;
  print_endline tip
