#!/bin/sh
# Bootstrap a fresh project on the Sonar instance.
curl -u admin:admin https://sonar.example.com/api/projects/create \
  -d "name=demo&project=demo"
