# Root password recovery

If you ever forget the MySQL root password, the official recovery procedure
involves temporarily restarting `mysqld` with the privilege system disabled,
resetting the password, and then restarting normally. We deliberately do
**not** ship that flag in any config or unit file — it must only be set
interactively, by an operator, on a server that is firewalled to localhost.
