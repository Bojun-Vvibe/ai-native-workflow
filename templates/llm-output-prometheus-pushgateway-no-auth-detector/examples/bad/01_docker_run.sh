#!/usr/bin/env bash
# Bad: docker run publishes pushgateway 9091 with no auth config.
docker run -d -p 9091:9091 prom/pushgateway:v1.9.0
