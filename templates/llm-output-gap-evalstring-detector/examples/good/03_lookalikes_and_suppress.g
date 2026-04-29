# Identifiers that merely contain the substrings do not match.
MyEvalStringHelper := function(x) return x; end;
EvalStrings := [];   # plural, different identifier
xEvalString := 1;    # different prefix
NotReadAsFunction := function() return 0; end;
Print(MyEvalStringHelper("ok"), "\n");

# A vetted call suppressed inline.
result := EvalString("1+2");  # eval-ok
Print(result, "\n");
