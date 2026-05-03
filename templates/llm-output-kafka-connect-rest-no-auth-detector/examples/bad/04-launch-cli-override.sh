#!/usr/bin/env bash
# Launch Kafka Connect distributed worker, overriding the REST bind
# to listen on every interface so the dashboard "just works".
set -euo pipefail
exec /opt/kafka/bin/connect-distributed.sh \
  --override rest.host.name=0.0.0.0 \
  --override rest.advertised.host.name=connect.example.invalid \
  /etc/kafka-connect/connect-distributed.properties
