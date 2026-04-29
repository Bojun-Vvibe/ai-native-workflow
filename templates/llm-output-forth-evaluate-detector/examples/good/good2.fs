\ good2.fs — the word "EVALUATE" appears only inside a comment / string
\ This file does not actually call EVALUATE anywhere.
: doc ( -- )
  ." We do not call EVALUATE on user input here." cr
  ( historical note: EVALUATE used to be called INTERPRET )
;
