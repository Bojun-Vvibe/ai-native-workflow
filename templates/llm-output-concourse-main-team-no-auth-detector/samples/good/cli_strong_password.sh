#!/usr/bin/env bash
# Concourse web with a non-placeholder password and matching main-team binding.
exec concourse web \
  --external-url "https://ci.example.com" \
  --postgres-host pg.internal \
  --postgres-user concourse \
  --postgres-database atc \
  --add-local-user "admin:Zk7Q-vT9bN3mE8wRpL2x" \
  --main-team-local-user admin
