% bad6.pl — .pl file, but contains a Prolog directive so it is
% recognized as Prolog and scanned.  Multiple sinks in one file.
:- module(bad6, [a/1, b/2]).

a(G) :- call(G).
b(H, B) :- asserta((H :- B)).
