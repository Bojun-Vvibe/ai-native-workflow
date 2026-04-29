\ bad2.fs — EVALUATE on a buffer fetched from memory
: spawn-from-buf ( -- )
  user-buf @ count EVALUATE
;
