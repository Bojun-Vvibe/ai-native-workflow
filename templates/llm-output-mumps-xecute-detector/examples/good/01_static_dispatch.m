STATIC ; Static dispatch: no XECUTE, no @-indirection. The IF/ELSE
 ; ladder is the right tool for finite known commands.
 R "cmd: ",CMD
 I CMD="start" D START Q
 I CMD="stop"  D STOP Q
 W "unknown",! Q
START W "starting",! Q
STOP  W "stopping",! Q
