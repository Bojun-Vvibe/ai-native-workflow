#!/usr/bin/env bash
# Bad: master key explicitly empty in env file
export MEILI_MASTER_KEY=""
export MEILI_ENV="production"
./meilisearch
