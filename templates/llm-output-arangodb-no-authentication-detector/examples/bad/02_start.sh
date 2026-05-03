#!/bin/sh
# Quickstart from a blog post.
arangod \
  --server.endpoint tcp://0.0.0.0:8529 \
  --server.authentication false \
  --database.directory /var/lib/arangodb3
