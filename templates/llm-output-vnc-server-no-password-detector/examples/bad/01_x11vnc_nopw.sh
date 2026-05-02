#!/usr/bin/env bash
# Quickstart: share my X session with a coworker for screen-sharing.
x11vnc -display :0 -forever -nopw -shared
