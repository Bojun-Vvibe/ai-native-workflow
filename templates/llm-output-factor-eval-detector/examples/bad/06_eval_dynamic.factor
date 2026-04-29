USING: eval kernel sequences ;
IN: scratch.bad

: run-from-input ( prefix user-frag -- )
    " " glue eval( -- ) ;
