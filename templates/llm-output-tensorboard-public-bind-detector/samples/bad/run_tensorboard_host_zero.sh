#!/usr/bin/env bash
# Bad: equivalent shape using --host=0.0.0.0 instead of --bind_all.
tensorboard --logdir=./runs --host=0.0.0.0 --port=6006
