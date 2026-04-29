% good3.pro — audited use, suppressed with `% call-ok`
:- module(good3, [bootstrap/0]).

bootstrap :-
    Goal = write(starting),
    call(Goal).  % call-ok  Goal is a literal in source, not user input
