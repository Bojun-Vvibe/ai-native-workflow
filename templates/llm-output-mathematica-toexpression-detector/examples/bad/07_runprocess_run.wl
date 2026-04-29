(* RunProcess and Run shell out -- with a controlled string this is
   command injection. *)
cmd = $ScriptCommandLine[[2]];
RunProcess[{"sh", "-c", cmd}];
Run[cmd]
