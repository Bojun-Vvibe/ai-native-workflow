USING: io ;
IN: scratch.good

! A string named "eval(" appears only inside a literal we print.
! Nothing is parsed or executed.
: announce ( -- )
    "the eval( word is dangerous" print ;
