(* Multiline (* nested (* comments *) *) must mask their content
   completely, including any Get[] or ToExpression[] mention. *)
Print["before"]
(* outer comment
   (* inner with ToExpression[bad] and Get["bad"] *)
   still in outer with << bad too
*)
Print["after"]
