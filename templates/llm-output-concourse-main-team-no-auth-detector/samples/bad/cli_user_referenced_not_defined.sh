#!/usr/bin/env bash
# Quickstart Concourse web — references the 'admin' local user for the
# main team but never actually creates that user. Concourse versions
# differ in how they handle this; the safe assumption is "auth is
# effectively bypassed" and we flag it.
exec concourse web \
  --external-url "https://ci.example.com" \
  --postgres-host pg.internal \
  --postgres-user concourse \
  --postgres-database atc \
  --main-team-local-user admin
