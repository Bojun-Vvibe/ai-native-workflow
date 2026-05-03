#!/usr/bin/env bash
# Default-secure: bind only to loopback; reverse proxy handles TLS+auth.
exec rethinkdb --bind 127.0.0.1
