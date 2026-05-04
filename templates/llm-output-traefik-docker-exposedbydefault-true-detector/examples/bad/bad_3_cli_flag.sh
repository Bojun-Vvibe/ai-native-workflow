#!/bin/sh
# launch traefik with the docker provider via CLI flags
docker run -d --name traefik \
  -p 80:80 -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  traefik:v3.0 \
  --api.dashboard=true \
  --providers.docker=true \
  --providers.docker.exposedByDefault=true \
  --entrypoints.web.address=:80
