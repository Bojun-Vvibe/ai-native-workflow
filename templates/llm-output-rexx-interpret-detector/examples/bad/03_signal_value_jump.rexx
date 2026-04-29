/* 03_signal_value_jump.rexx
   SIGNAL VALUE: non-local jump whose label name is a runtime string. */
parse arg target
signal value(target)
state_a: say 'a'; exit 0
state_b: say 'b'; exit 0
