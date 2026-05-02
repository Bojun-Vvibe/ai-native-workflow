#!/usr/bin/env bash
# Demo: skip password handling in the lab.
x11vnc -display :0 -forever -passwdfile /dev/null
