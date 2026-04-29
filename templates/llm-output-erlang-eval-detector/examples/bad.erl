%% bad.erl — every line below should trigger the detector.
-module(bad).
-export([go/1]).

go(Src) ->
    {ok, Tokens, _} = erl_scan:string(Src),                 %% bad-1: lexer-from-string
    {ok, Forms}     = erl_parse:parse_exprs(Tokens),        %% bad-2: parser-from-tokens
    {value, V, _}   = erl_eval:exprs(Forms, []),            %% bad-3: erl_eval entry
    _ = erl_eval:expr(hd(Forms), []),                       %% bad-4: erl_eval:expr/2
    _ = erl_eval:expr_list(Forms, [], []),                  %% bad-5: erl_eval:expr_list
    _ = erl_parse:parse_term(Tokens),                       %% bad-6: parse_term
    {ok, _M, Bin} = compile:forms(Forms),                   %% bad-7: runtime compile
    {module, M2}  = code:load_binary(my_mod, "my_mod.erl", Bin), %% bad-8: runtime load
    _ = dynamic_compile:from_string(Src),                   %% bad-9: contrib helper
    _ = dynamic_compile:load_from_string(Src),              %% bad-10: contrib helper
    Mod = list_to_atom("some_mod"),                         %% bad-11: atom-from-string apply
    Fun = list_to_atom("some_fun"),
    apply(Mod, Fun, []),                                    %% (paired with above)
    apply(list_to_atom("foo"), bar, []),                    %% bad-12: explicit apply form
    V.
