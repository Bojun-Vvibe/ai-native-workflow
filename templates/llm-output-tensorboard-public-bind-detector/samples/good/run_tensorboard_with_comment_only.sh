#!/usr/bin/env bash
# Good: the dangerous flag appears only inside a `#` comment that
# documents what NOT to do. The detector strips comments before
# matching.
# Do NOT do this on a shared box: tensorboard --bind_all
tensorboard --logdir runs/ --port 6006
