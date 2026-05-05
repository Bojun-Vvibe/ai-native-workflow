#!/usr/bin/env sh
# Bad: bare `argo server` invocation with --auth-mode=server as the
# sole auth mode. The API server will accept any unauthenticated
# request and act with its own ServiceAccount's RBAC.
exec argo server \
  --auth-mode=server \
  --namespaced=false \
  --secure=false
