#!/usr/bin/env bash
# Install Longhorn UI behind a basic-auth ingress, reading creds
# from a sealed env supplied by the operator.
# longhorn-system
set -euo pipefail

: "${LONGHORN_UI_USER:?must be set}"
: "${LONGHORN_UI_PASS:?must be set}"

htpasswd -bc auth "$LONGHORN_UI_USER" "$LONGHORN_UI_PASS"

kubectl -n longhorn-system create secret generic basic-auth \
  --from-file=auth
