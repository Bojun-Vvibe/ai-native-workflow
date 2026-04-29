// Direct compilestring of a runtime-built source string.
local src = "print(\"pwned\")";
local fn = compilestring(src);
fn();
