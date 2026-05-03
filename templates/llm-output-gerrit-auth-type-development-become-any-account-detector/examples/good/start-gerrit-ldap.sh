#!/usr/bin/env bash
# Launch GerritCodeReview with LDAP auth — safe production form.
set -euo pipefail
exec java -jar /var/gerrit/bin/gerrit.war daemon \
    -d /var/gerrit \
    -c auth.type=LDAP \
    -c ldap.server=ldaps://ldap.example.com \
    -c gerrit.canonicalWebUrl=https://gerrit.example.com/
