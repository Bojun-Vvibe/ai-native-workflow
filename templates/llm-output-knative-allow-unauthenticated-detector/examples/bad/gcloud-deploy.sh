#!/usr/bin/env bash
# Deploy a Knative service to Cloud Run for Anthos.
# run.googleapis.com managed flavour.
set -euo pipefail

gcloud run deploy hello-knative \
  --image gcr.io/example/hello \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
