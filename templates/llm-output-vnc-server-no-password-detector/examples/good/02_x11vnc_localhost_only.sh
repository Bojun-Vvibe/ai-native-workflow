#!/usr/bin/env bash
# Local-only debug: VNC bound to loopback, surfaced via SSH tunnel.
x11vnc -display :0 -forever -nopw -localhost
