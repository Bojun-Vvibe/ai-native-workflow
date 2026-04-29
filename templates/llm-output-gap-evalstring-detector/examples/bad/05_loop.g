# Loop applies EvalString to each line of an input file.
ApplyAll := function(lines)
    local line;
    for line in lines do
        EvalString(line);
    od;
end;
