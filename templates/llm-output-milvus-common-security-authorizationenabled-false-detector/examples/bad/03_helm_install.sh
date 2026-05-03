#!/usr/bin/env bash
# Bad: helm install with --set turning auth off explicitly.
# EXAMPLE_PASSWORD_DO_NOT_USE — fake values only.
set -euo pipefail
helm upgrade --install milvus milvus/milvus \
  --namespace milvus --create-namespace \
  --set cluster.enabled=true \
  --set extraConfigFiles.user\\.yaml.common.security.authorizationEnabled=false \
  --set service.type=LoadBalancer
