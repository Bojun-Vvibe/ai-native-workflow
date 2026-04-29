% bad3.prolog — call/N partial-application sink
:- module(bad3, [dispatch/3]).

dispatch(F, X, Y) :-
    call(F, X, Y).
