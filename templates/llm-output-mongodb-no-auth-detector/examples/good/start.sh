#!/usr/bin/env bash
# Good: explicit --auth flag.
set -e
mongod --dbpath /data/db --bind_ip 0.0.0.0 --auth &
wait
