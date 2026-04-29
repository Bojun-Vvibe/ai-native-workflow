# Mentions inside string literals are ignored.
doc := "EvalString(s) is a foot-gun; use a real parser.";
warn := "ReadAsFunction(InputTextString(x)) is the same idea.";
Print(doc, "\n", warn, "\n");
