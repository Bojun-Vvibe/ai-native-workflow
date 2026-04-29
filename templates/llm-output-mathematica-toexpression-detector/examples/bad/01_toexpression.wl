(* ToExpression[s] parses s as Wolfram source and evaluates it. *)
userInput = InputString["expr> "];
result = ToExpression[userInput];
Print[result]
