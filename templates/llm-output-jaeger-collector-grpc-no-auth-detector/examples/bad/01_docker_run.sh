#!/usr/bin/env bash
# Quick-start that the team copy-pasted from a tutorial.
# Publishes the OTLP gRPC ingest port to every interface with no auth.
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 14250:14250 \
  jaegertracing/all-in-one:1.57
