#!/usr/bin/env bash
# bootstrap listmonk on a fresh host
export LISTMONK_ADMIN_USER="admin"
export LISTMONK_ADMIN_PASSWORD="changeme"
docker run -d --name listmonk -p 9000:9000 \
  -e LISTMONK_ADMIN_USER \
  -e LISTMONK_ADMIN_PASSWORD \
  listmonk/listmonk:latest
