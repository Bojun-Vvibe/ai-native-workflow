\ bad3.fth — INTERPRET called directly on a user buffer
: shell-loop ( -- )
  begin
    refill while
    INTERPRET
  repeat
;
