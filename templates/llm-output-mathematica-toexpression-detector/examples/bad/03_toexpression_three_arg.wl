(* Three-arg ToExpression -- the head wraps the *result*; the
   string is still evaluated. *)
userInput = Import["!cat /tmp/cmd", "String"];
res = ToExpression[userInput, InputForm, Hold];
Print[res]
