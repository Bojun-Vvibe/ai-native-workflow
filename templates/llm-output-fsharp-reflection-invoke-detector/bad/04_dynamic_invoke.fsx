module DelegateDance

open System

let runDelegate (d: Delegate) (args: obj[]) =
    // DynamicInvoke loses type safety and bypasses the F# type system.
    d.DynamicInvoke(args)

let readField (target: obj) (fieldName: string) =
    let f = target.GetType().GetField(fieldName)
    f.GetValue(target)
