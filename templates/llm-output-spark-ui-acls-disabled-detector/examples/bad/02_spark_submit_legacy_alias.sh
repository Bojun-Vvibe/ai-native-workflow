#!/usr/bin/env bash
set -euo pipefail

exec spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --conf spark.ui.acls.enable=false \
  --conf spark.eventLog.enabled=true \
  --class com.example.batch.NightlyJob \
  /opt/jobs/nightly.jar
