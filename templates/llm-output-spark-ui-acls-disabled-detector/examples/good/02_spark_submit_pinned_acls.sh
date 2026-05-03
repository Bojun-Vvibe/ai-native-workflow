#!/usr/bin/env bash
set -euo pipefail

# Note: spark.acls.enable=false would expose the driver UI; we leave
# it at the default (true) and pin admins via spark.admin.acls.
exec spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --conf spark.admin.acls=ops-team \
  --conf spark.modify.acls=etl-svc \
  --class com.example.batch.NightlyJob \
  /opt/jobs/nightly.jar
