#!/bin/sh
set -eu
gitlab-runner register \
  --non-interactive \
  --url "https://gitlab.example.com/" \
  --registration-token "$REG_TOKEN" \
  --executor "docker" \
  --docker-image "alpine:3.19" \
  --docker-privileged \
  --description "shared docker runner"
