USING: eval io ;
IN: scratch.bad

: run-snippet ( -- )
    "1 2 + ." eval( -- ) ;
