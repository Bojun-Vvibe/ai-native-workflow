#!/usr/bin/env bash
# Bound strictly to loopback; an envoy/oauth2-proxy in front handles
# authn before forwarding to the collector.
docker run -d --name jaeger \
  -p 127.0.0.1:14250:14250 \
  -p 127.0.0.1:4317:4317 \
  jaegertracing/all-in-one:1.57
