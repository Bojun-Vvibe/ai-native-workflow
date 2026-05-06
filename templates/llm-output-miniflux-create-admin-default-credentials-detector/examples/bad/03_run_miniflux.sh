#!/usr/bin/env bash
# Boot miniflux with bootstrap admin
set -e
docker run -d \
  --name miniflux \
  -p 8080:8080 \
  -e DATABASE_URL="postgres://miniflux:secret@db/miniflux?sslmode=disable" \
  -e RUN_MIGRATIONS=1 \
  -e CREATE_ADMIN=1 \
  -e ADMIN_USERNAME=miniflux \
  -e ADMIN_PASSWORD=miniflux \
  miniflux/miniflux:latest
