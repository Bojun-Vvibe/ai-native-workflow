(* Safe dispatch over a small allowlist of known operations. *)
op = $ScriptCommandLine[[2]];
result = Switch[op,
  "square", Function[x, x^2],
  "cube",   Function[x, x^3],
  _,        Function[x, $Failed]
][3];
Print[result]
