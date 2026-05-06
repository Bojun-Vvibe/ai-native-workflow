#!/usr/bin/env bash
# bootstrap umami on a single host
export APP_SECRET="umami"
export DATABASE_URL="postgresql://umami:umami@localhost/umami"
docker run -d --name umami -p 3000:3000 \
  -e DATABASE_URL \
  -e APP_SECRET \
  ghcr.io/umami-software/umami:postgresql-latest
