#!/usr/bin/env bash
# Install Longhorn UI behind a basic-auth ingress.
# longhorn-system / longhorn-frontend
set -euo pipefail

# Generate the htpasswd file with the documented quickstart creds.
htpasswd -bc auth admin admin

kubectl -n longhorn-system create secret generic basic-auth \
  --from-file=auth
