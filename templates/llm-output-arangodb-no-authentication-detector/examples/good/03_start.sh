#!/bin/sh
# Production startup with authentication on and a real root password
# coming from a secret-mounted file.
arangod \
  --server.endpoint tcp://0.0.0.0:8529 \
  --server.authentication true \
  --database.directory /var/lib/arangodb3
