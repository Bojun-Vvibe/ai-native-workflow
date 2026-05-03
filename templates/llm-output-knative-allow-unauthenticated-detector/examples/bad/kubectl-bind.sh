#!/usr/bin/env bash
# Bind the unauthenticated group to a Knative serving role.
# (Found in too many "knative quickstart" gists.)
set -euo pipefail

kubectl create clusterrolebinding knative-public \
  --clusterrole=serving.knative.dev-invoker \
  --group=system:unauthenticated
