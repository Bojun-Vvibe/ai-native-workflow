#!/usr/bin/env bash
# start-flink-jobmanager.sh -- LLM-generated Kubernetes initContainer
# Standalone Flink JobManager with REST bound to all interfaces.

set -e
export FLINK_HOME=/opt/flink

"$FLINK_HOME/bin/jobmanager.sh" start-foreground \
  -Drest.bind-address=0.0.0.0 \
  -Djobmanager.rpc.address=0.0.0.0 \
  -Dtaskmanager.numberOfTaskSlots=4 \
  -Dparallelism.default=2
