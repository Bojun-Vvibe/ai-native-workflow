-- Bad: implicit-call ``load`` with a variable
src = arg[1]
chunk = load src
chunk! if chunk
