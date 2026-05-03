#!/usr/bin/env bash
# Quickstart launch from a tutorial — exposes the cluster to the world.
set -euo pipefail
mkdir -p /var/lib/mongo
mongod --bind_ip_all --dbpath /var/lib/mongo --port 27017 --fork \
  --logpath /var/log/mongodb/mongod.log
