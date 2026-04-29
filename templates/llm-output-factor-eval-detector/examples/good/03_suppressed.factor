USING: eval ;
IN: scratch.good

: explicitly-trusted-snippet ( -- )
    "1 2 + ." eval( -- ) ! factor-eval-ok
    ;
