% bad1.pro — call/1 on a runtime-built goal
:- module(bad1, [run/1]).

run(UserAtom) :-
    term_to_atom(Goal, UserAtom),
    call(Goal).
