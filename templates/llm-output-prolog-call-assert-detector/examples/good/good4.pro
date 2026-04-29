% good4.pro — predicates whose names merely contain "call" or
% "assert" as a substring are NOT flagged because the regex requires
% a non-word-character on the left.
:- module(good4, [mycall/1, asserter/1, recall/1]).

mycall(X)   :- write(X), nl.
asserter(X) :- write(X), nl.
recall(X)   :- write(X), nl.
