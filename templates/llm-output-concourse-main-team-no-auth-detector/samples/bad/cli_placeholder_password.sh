#!/usr/bin/env bash
# Concourse web with the local admin user set to the literal upstream
# placeholder password. Anyone who reads the docs has these creds.
exec concourse web \
  --external-url "https://ci.example.com" \
  --postgres-host pg.internal \
  --postgres-user concourse \
  --postgres-database atc \
  --add-local-user admin:admin \
  --main-team-local-user admin
