#!/usr/bin/env bash
# normal startup — privileges enforced, root password from secret
docker run -d --name db \
  -e MYSQL_ROOT_PASSWORD_FILE=/run/secrets/mysql_root \
  -p 127.0.0.1:3306:3306 \
  mysql:8
