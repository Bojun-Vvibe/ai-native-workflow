(* ToExpression and Get inside string literals must not flag. *)
docs = "Use ToExpression[s] to evaluate s as Wolfram source.";
warn = "Get[path] reads a file and evaluates it.";
Print[docs];
Print[warn]
