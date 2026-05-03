#!/usr/bin/env bash
# Bad: bare invocation, no key flag, no env var in scope
set -e
cd /opt/search
./meilisearch --http-addr 0.0.0.0:7700 --env production
