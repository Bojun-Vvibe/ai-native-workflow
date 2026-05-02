#!/bin/sh
# Use a per-CI Sonar token (issued under /account/security) sourced
# from the secret store, not the bootstrap admin password.
: "${SONAR_TOKEN:?SONAR_TOKEN must be set}"
curl -u "${SONAR_TOKEN}:" https://sonar.example.com/api/projects/create \
  -d "name=demo&project=demo"
