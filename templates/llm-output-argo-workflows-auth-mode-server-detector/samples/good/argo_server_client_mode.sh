#!/usr/bin/env sh
# Good: explicit --auth-mode=client (the default). Authenticated bearer
# tokens are required for every API request.
exec argo server \
  --auth-mode=client \
  --namespaced=false
