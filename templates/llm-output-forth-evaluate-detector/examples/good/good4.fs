\ good4.fs — words whose names merely contain "evaluate" / "interpret"
\ are NOT flagged because the regex requires a whitespace-bounded
\ exact bareword match.
: my-evaluator ( x -- y ) 2 * ;
: reinterpret-bits ( a -- b ) 1+ ;
: includedness ( -- ) ." ok" cr ;
