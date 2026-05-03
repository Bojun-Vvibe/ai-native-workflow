#!/usr/bin/env bash
# Install Rancher Manager via Helm with the documented bootstrap
# default. After this runs, the first browser to reach the UI gets
# cluster-admin on every cluster Rancher manages.
set -euo pipefail

helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
helm repo update

kubectl create namespace cattle-system || true

helm upgrade --install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --set hostname=rancher.example.com \
  --set bootstrapPassword=admin \
  --set ingress.tls.source=letsEncrypt \
  --set replicas=3
