#!/usr/bin/env bash
# Good: bound to the loopback IP literal. Same effect as
# --host=localhost; just different spelling.
tensorboard --logdir=./runs --host=127.0.0.1 --port=6006
