/* 04_address_value_shell.rexx
   ADDRESS VALUE switches the host environment to a runtime-chosen
   string, so the very next host-command literal is dispatched to a
   shell whose identity the model picked at runtime. */
parse arg env_name
address value(env_name)
'ls -la'
exit 0
