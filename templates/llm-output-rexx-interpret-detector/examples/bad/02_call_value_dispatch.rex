/* 02_call_value_dispatch.rex
   CALL with a name computed at runtime via VALUE(). The handler
   string came in from the environment, so this is dynamic dispatch
   to an attacker-controlled label. */
handler = value('HANDLER_NAME', , 'ENVIRONMENT')
parse arg payload
call value(handler) payload
exit 0
