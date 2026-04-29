module DynamicCall

open System

let callByName (target: obj) (name: string) (args: obj[]) =
    let t = target.GetType()
    let mi = t.GetMethod(name)
    mi.Invoke(target, args)
