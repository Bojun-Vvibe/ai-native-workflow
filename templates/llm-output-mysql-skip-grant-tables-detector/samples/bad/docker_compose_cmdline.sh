#!/usr/bin/env bash
# bring up mysql with auth disabled so the migration script can run
docker run -d --name db \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=1 \
  -p 3306:3306 \
  mysql:8 \
  --skip-grant-tables --skip-networking=0
