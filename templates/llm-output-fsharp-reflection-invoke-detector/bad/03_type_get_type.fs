// Looks "fancy" — runtime type lookup by string + dynamic construction.
module DynamicConstruct

open System

let make (typeFullName: string) (args: obj[]) =
    let t = Type.GetType(typeFullName)
    Activator.CreateInstance(t, args)

let getProp (target: obj) (propName: string) =
    let p = target.GetType().GetProperty(propName)
    p.GetValue(target)
