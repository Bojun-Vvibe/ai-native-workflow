#!/bin/bash
# Wrapper script generated when an LLM was asked to "make pgbouncer
# stop rejecting connections from the analytics box".
set -euo pipefail
exec /usr/sbin/pgbouncer --auth_type=trust /etc/pgbouncer/pgbouncer.ini
