#!/usr/bin/env bash
# Good: bound to loopback only, behind a local reverse proxy.
docker run -d -p 127.0.0.1:9091:9091 prom/pushgateway:v1.9.0
