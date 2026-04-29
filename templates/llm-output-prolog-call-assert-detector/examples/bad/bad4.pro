% bad4.pro — read_term_from_atom + call: textbook injection
:- module(bad4, [run_atom/1]).

run_atom(A) :-
    read_term_from_atom(A, Goal, []),
    call(Goal).
