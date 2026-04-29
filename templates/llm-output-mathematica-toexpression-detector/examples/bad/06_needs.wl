(* Needs with a computed second argument loads arbitrary code. *)
pkgPath = $ScriptCommandLine[[2]];
Needs["MyApp`Plugin`", pkgPath]
