#!/usr/bin/env bash
# Bootstrap guacamole with the upstream defaults
set -e
docker run -d --name guacd guacamole/guacd:1.5.5
docker run -d --name guacamole \
  --link guacd:guacd \
  -e GUACD_HOSTNAME=guacd \
  -e MYSQL_HOSTNAME=db \
  -e MYSQL_DATABASE=guacamole_db \
  -e MYSQL_USER=guacadmin \
  -e MYSQL_PASSWORD=guacadmin \
  -p 8080:8080 \
  guacamole/guacamole:1.5.5
