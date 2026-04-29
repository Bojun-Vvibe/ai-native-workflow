// The string "compilestring(src)" appears only inside a literal.
local doc = "do not call compilestring(src) on attacker input";
print(doc);

// Identifiers that merely contain "compilestring" do not match.
local my_compilestring_helper = "ok";
function compilestringify(x) { return x.tostring(); }
