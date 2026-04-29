# ReadAsFunction(InputTextString(...)) is the read-string variant.
LoadHook := function(src)
    local f;
    f := ReadAsFunction(InputTextString(src));
    return f();
end;
