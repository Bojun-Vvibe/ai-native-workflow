' bad: Eval as a calculator over user input
Dim formula : formula = Request("f")
result = Eval(formula)
WScript.Echo result
