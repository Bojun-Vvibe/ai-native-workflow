%% good.erl — none of these should trigger the detector.
-module(good).
-export([go/2, dispatch/2, helper/1]).

%% Comment mentioning erl_eval:exprs( and compile:forms( and
%% dynamic_compile:from_string( — all inside a `%` comment, so masked.

%% String literals containing the dangerous identifiers — masked.
helper(_) ->
    Doc = "see erl_eval:exprs/2 and compile:forms/1 for details",
    Doc.

%% Plain apply with literal atoms — normal dispatch, not eval.
go(X, Y) ->
    apply(lists, sum, [[X, Y]]).

%% list_to_atom on its own line, with no `:` apply — pure conversion,
%% not flagged.
dispatch(Name, Arg) ->
    A = list_to_atom(Name),
    {converted, A, Arg}.

%% Explicit suppression for a fixture-only path.
fixture(Src) ->
    erl_eval:exprs(Src, []).  %% eval-string-ok
