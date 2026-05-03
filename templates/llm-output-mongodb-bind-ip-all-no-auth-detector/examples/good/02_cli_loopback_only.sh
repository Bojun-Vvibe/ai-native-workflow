#!/usr/bin/env bash
# Local-only dev launch; no remote interface exposed.
set -euo pipefail
mkdir -p /var/lib/mongo
mongod --bind_ip 127.0.0.1 --dbpath /var/lib/mongo --port 27017 --fork \
  --logpath /var/log/mongodb/mongod.log
