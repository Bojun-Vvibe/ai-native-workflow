#!/usr/bin/env bash
# Production-style screen sharing: passwd file required.
x11vnc -display :0 -forever -rfbauth /etc/vnc/passwd -ssl SAVE
