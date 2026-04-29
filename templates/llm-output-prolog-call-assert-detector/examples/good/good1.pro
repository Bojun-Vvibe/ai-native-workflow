% good1.pro — no dynamic dispatch.  Closed allowlist of goals.
:- module(good1, [run/1]).

run(greet) :- write(hello), nl.
run(quit)  :- halt.
