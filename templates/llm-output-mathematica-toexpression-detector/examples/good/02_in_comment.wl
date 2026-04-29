(* ToExpression and Get mentioned only in comments must not flag.
   Example of unsafe code we are warning *against*:
     ToExpression[userInput]
     Get[pluginPath]
     << somePackage
*)
Print["hello"]
