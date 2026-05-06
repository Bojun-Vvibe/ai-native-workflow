#!/usr/bin/env bash
# This is a Concourse *worker* invocation, not web. Auth flags do not
# apply — workers authenticate to TSA via SSH keys. Out of scope.
exec concourse worker \
  --work-dir /opt/concourse-worker \
  --tsa-host web.internal:2222 \
  --tsa-public-key /etc/concourse/tsa_host_key.pub \
  --tsa-worker-private-key /etc/concourse/worker_key
