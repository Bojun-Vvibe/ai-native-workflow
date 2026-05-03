#!/usr/bin/env bash
# Grant run.invoker on a Knative service to a single named user only.
set -euo pipefail

gcloud run services add-iam-policy-binding hello-knative \
  --region=us-central1 \
  --member=user:ops-oncall@example.test \
  --role=roles/run.invoker
