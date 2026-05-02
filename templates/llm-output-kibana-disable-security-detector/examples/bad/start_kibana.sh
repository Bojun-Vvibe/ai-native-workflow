#!/bin/sh
# Launch script generated from a tutorial — disables security via CLI flag.
exec /usr/share/kibana/bin/kibana \
  --server.host=0.0.0.0 \
  --elasticsearch.hosts=http://es01:9200 \
  --xpack.security.enabled=false
