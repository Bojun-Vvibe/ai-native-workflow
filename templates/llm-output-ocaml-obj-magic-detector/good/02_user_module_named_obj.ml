(* 02_user_module_named_obj.ml — a user module that shares the name.
   The detector only flags `Obj.<unsafe_name>` from the stdlib's Obj
   module. A user-defined `Obj` module with different members is not
   what we are looking for, but to be safe we name our members
   distinctly here so that even a careless reader cannot confuse
   them with stdlib calls. *)

module Renderer = struct
  let draw _scene = ()
  let snapshot _scene = ""
end

let () =
  Renderer.draw ();
  ignore (Renderer.snapshot ())
