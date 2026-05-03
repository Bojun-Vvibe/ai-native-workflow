#!/usr/bin/env bash
# Bad: shell script that exports the anonymous flag with no other
# auth flag. EXAMPLE_PASSWORD_DO_NOT_USE — fake values only.
set -euo pipefail
export QUERY_DEFAULTS_LIMIT=25
export AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
export PERSISTENCE_DATA_PATH=/var/lib/weaviate
exec weaviate --host 0.0.0.0 --port 8080 --scheme http
