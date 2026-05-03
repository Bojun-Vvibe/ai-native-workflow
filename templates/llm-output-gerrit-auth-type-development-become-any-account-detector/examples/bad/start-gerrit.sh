#!/usr/bin/env bash
# Launch GerritCodeReview daemon for local container.
set -euo pipefail
exec java -jar /var/gerrit/bin/gerrit.war daemon \
    -d /var/gerrit \
    -c auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT \
    -c gerrit.canonicalWebUrl=http://gerrit.local/
