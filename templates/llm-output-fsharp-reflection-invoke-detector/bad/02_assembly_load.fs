module Loader

open System
open System.Reflection

let loadAndRun (asmPath: string) (typeName: string) (methodName: string) =
    let asm = Assembly.LoadFrom(asmPath)
    let t = asm.GetType(typeName)
    let inst = Activator.CreateInstance(t)
    t.InvokeMember(methodName, BindingFlags.InvokeMethod, null, inst, [||])
