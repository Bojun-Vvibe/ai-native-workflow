% bad5.pro — retractall on a user-controlled functor
:- module(bad5, [wipe/1]).

wipe(Functor) :-
    retractall(Functor).
