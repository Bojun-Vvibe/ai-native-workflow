#!/usr/bin/env bash
# Good: explicit --host=localhost. Equivalent to the default but
# spelled out for reviewers.
tensorboard --logdir=./runs --host=localhost --port=6006
