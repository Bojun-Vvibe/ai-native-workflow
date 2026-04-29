' good: lookalike identifiers that share a prefix but are not the keyword
Function ExecuteWorkbook(name)
    ExecuteWorkbook = "ran:" & name
End Function

Function EvalScore(x)
    EvalScore = x * 2
End Function

Dim MyExecutor : MyExecutor = "label"
WScript.Echo ExecuteWorkbook("a")
WScript.Echo EvalScore(3)
WScript.Echo MyExecutor
