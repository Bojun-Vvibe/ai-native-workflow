#!/usr/bin/env bash
# Deploy a Knative service requiring authentication.
# run.googleapis.com managed flavour.
set -euo pipefail

gcloud run deploy hello-knative \
  --image gcr.io/example/hello \
  --platform managed \
  --region us-central1 \
  --no-allow-unauthenticated
