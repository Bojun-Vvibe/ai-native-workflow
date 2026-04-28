(* 01_pure_safe.ml — straight-line, type-safe code. *)
let add (a : int) (b : int) : int = a + b

let greet name = Printf.sprintf "Hello, %s!" name

let () =
  print_endline (greet "world");
  Printf.printf "%d\n" (add 2 3)
