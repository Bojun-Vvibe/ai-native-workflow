#!/bin/ksh
# Safe dispatch over a small allowlist of known operations.
case "$1" in
  start) systemctl start myapp ;;
  stop)  systemctl stop  myapp ;;
  *)     printf 'unknown\n' >&2; exit 2 ;;
esac
