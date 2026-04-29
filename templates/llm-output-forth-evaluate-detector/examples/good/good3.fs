\ good3.fs — audited use, suppressed with `\ evaluate-ok`
: bootstrap ( -- )
  s" : init ; init" EVALUATE  \ evaluate-ok  intentional, constant string, audited
;
