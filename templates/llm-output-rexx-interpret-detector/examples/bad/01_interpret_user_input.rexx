/* 01_interpret_user_input.rexx
   Classic INTERPRET-of-user-input: pull a line from STDIN and run it
   as REXX source. This is exec() for the REXX VM. */
parse pull cmd
interpret cmd
say 'done'
exit 0
