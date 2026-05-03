#!/usr/bin/env bash
# Install Rancher Manager via Helm. The bootstrap password is read
# from an existing sealed secret and rotated on first login.
#
# NB: Earlier versions of the docs used --set bootstrapPassword=admin;
# never commit that. Pull from your secret manager instead.
set -euo pipefail

PASS=$(kubectl get secret -n cattle-system rancher-bootstrap \
  -o jsonpath='{.data.password}' | base64 -d)

helm upgrade --install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --set hostname=rancher.example.com \
  --set bootstrapPassword="${PASS}" \
  --set ingress.tls.source=letsEncrypt
