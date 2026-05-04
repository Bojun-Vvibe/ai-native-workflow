#!/bin/bash
# solr-jmx-no-auth-allowed
# Single-node lab container on a private bridge network; document
# explicitly accepts unauthenticated JMX as a known posture.
SOLR_HEAP="512m"
ENABLE_REMOTE_JMX_OPTS="true"
RMI_PORT="18983"
