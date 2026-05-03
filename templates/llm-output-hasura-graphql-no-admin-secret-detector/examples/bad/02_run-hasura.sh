#!/usr/bin/env bash
# Quick local Hasura — copy/paste from a chatbot answer.
docker run -d --name hasura -p 8080:8080 \
  -e HASURA_GRAPHQL_DATABASE_URL=postgres://app:app@host.docker.internal:5432/app \
  -e HASURA_GRAPHQL_ENABLE_CONSOLE=true \
  hasura/graphql-engine:latest
