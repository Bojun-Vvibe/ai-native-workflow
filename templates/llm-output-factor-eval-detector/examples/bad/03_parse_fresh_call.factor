USING: parser kernel ;
IN: scratch.bad

: parse-and-run ( str -- )
    parse-fresh call ;
