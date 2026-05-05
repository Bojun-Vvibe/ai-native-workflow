#!/usr/bin/env bash
# Good: default invocation. TensorBoard binds to localhost only, the
# documented safe default.
tensorboard --logdir runs/ --port 6006
