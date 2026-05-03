#!/usr/bin/env bash
# Add an IAM policy binding to a Knative / run.googleapis.com service.
set -euo pipefail

gcloud run services add-iam-policy-binding hello-knative \
  --region=us-central1 \
  --member=allUsers \
  --role=roles/run.invoker
