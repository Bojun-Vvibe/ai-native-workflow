// Verbatim strings @"..." also mask their contents.
local sample = @"compilestring(src)() is dangerous";
print(sample);

// A vetted call suppressed inline.
local fn = compilestring("return 42"); // eval-ok
print(fn());
