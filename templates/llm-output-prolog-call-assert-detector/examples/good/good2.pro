% good2.pro — the words "call" and "assert" appear only inside
% comments and strings.  They must NOT be flagged.
%
% NOTE: do not use call(Goal) on user input — see the README for
% detail.  Same for assertz(Clause).
:- module(good2, [doc/0]).

doc :-
    write('We never call(Goal) here.'), nl,
    write("Likewise, no assertz(_) at runtime."), nl.
