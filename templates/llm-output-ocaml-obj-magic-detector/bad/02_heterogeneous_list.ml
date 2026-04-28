(* 02_heterogeneous_list.ml — fake existential via Obj.magic. *)
type any = Any : 'a -> any

let unwrap_int (Any x) : int = Obj.magic x

let xs = [Any 1; Any "two"; Any 3.0]
let _ = List.map unwrap_int xs
