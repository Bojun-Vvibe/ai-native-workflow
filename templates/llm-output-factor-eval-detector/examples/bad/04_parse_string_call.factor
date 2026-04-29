USING: parser kernel ;
IN: scratch.bad

: parse-string-and-run ( str -- )
    parse-string call ;
