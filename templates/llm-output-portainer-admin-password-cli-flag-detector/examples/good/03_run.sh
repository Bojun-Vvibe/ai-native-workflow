#!/bin/sh
# Bootstrap with first-run UI; no admin password on argv.
# An operator will set the password via the web UI within 5 minutes
# (Portainer's default initialization-window).
docker run -d \
  -p 9443:9443 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  --name portainer \
  portainer/portainer-ce:latest
