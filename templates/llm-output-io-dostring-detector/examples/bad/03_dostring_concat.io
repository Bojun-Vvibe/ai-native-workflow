// Concatenates user input into the source string.
name := File standardInput readLine
Lobby doString("writeln(\"hello, \" .. " .. name .. ")")
