' good: doc strings that mention Execute / Eval inside literals
Dim help1 : help1 = "Do not use Execute on user input."
Dim help2 : help2 = "Eval(formula) is dangerous; use a parser."
Dim help3 : help3 = "ExecuteGlobal also bypasses scope rules."
WScript.Echo help1
WScript.Echo help2
WScript.Echo help3
