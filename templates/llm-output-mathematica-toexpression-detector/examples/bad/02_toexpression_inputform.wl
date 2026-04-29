(* ToExpression with explicit InputForm still evaluates. *)
userInput = $ScriptCommandLine[[2]];
result = ToExpression[userInput, InputForm];
Print[result]
