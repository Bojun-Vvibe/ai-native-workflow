\ good1.fs — execute a precompiled XT, no re-parse
: greet ( -- ) ." hello" cr ;
: run ( -- ) ['] greet EXECUTE ;
