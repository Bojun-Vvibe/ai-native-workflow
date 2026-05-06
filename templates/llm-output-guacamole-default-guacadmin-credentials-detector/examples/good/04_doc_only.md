# Apache Guacamole hardening notes

The upstream `guacamole-auth-jdbc-*` init script seeds a single
admin user `guacadmin` with password `guacadmin` (SHA-256 hash
`CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960`).

Operators MUST log in once, create a per-operator admin account,
then delete the `guacadmin` row before exposing port `8080` to
anything other than `127.0.0.1`.

This file is prose only; `.md` is excluded from scanning.
