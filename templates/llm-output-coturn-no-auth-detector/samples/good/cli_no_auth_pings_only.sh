#!/bin/sh
# turnserver — auth on; we only suppress the ping-auth keepalive.
exec /usr/bin/turnserver \
  --listening-port=3478 \
  --realm=turn.example.com \
  --lt-cred-mech \
  --no-auth-pings \
  --min-port=49152 --max-port=65535
