/* 01_static_dispatch.rexx
   Static label dispatch: no INTERPRET, no VALUE, no indirect names.
   A SELECT block is the right tool for finite known commands. */
parse arg cmd
select
    when cmd = 'start' then call do_start
    when cmd = 'stop'  then call do_stop
    otherwise say 'unknown command:' cmd
end
exit 0

do_start: say 'starting'; return
do_stop:  say 'stopping'; return
