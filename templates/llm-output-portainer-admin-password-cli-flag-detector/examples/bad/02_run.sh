#!/bin/sh
# Quickstart from a copy-pasted blog post.
docker run -d \
  -p 9000:9000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name portainer \
  portainer/portainer-ce:latest \
  --admin-password='changeme123'
