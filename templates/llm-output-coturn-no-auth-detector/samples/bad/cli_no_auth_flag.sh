#!/bin/sh
# Bring up coturn for the dev WebRTC rig.
exec /usr/bin/turnserver \
  --listening-port=3478 \
  --realm=turn.example.com \
  --no-auth \
  --no-auth-pings \
  --min-port=49152 --max-port=65535
