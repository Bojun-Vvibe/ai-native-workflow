(*
   Interface-based dispatch. The strings "GetMethod" and "Invoke"
   appear inside this block comment and inside a verbatim string,
   and must NOT trigger the detector.
*)
module InterfaceDispatch

type IGreeter =
    abstract member Greet : string -> string

type EnglishGreeter() =
    interface IGreeter with
        member _.Greet name = "Hello, " + name

let banner = @"This file mentions Type.GetMethod and InvokeMember inside a verbatim string."

let greet (g: IGreeter) name = g.Greet name
