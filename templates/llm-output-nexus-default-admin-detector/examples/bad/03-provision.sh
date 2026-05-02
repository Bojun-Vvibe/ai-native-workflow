#!/usr/bin/env bash
set -euo pipefail
# Provision the admin password after first boot.
curl -u admin:admin123 -X PUT \
  -H 'Content-Type: text/plain' \
  -d 'admin123' \
  http://nexus.local:8081/service/rest/v1/security/users/admin/change-password
