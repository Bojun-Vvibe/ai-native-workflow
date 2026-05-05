#!/usr/bin/env bash
# Bad: classic LLM "expose TensorBoard to my laptop" pattern. The
# --bind_all flag binds the dashboard to every interface with no
# authentication.
tensorboard --logdir runs/ --bind_all --port 6006
