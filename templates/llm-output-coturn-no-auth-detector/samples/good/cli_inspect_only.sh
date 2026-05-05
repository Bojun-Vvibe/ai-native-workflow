#!/bin/sh
# Read-only inspection of an existing TURN server.
turnutils_uclient -v -t -u alice -w "$TURN_PW" turn.example.com
turnutils_stunclient -p 3478 turn.example.com
