#!/usr/bin/env bash
# vnc-no-auth-allowed
# Lab fixture: explicitly opted in to no-auth VNC by the suppression marker.
x11vnc -display :0 -forever -nopw
