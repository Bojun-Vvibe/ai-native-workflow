#!/usr/bin/env bash
# Bad: space-separated --host 0.0.0.0 form. Same outcome as the `=`
# form; LLMs alternate between them depending on the surrounding
# style.
tensorboard --logdir ./runs --host 0.0.0.0
