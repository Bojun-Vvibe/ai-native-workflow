% bad2.pro — assertz of a clause whose body comes from outside
:- module(bad2, [install/2]).

install(Head, Body) :-
    assertz((Head :- Body)).
