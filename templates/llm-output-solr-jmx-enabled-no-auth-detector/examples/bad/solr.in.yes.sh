#!/bin/bash
# Operator notes claim "JMX is firewalled" but no authenticate=true
# or password.file is configured anywhere in the file.
SOLR_HEAP="1g"
ENABLE_REMOTE_JMX_OPTS=YES
RMI_PORT="18983"
SOLR_OPTS="$SOLR_OPTS -Dcom.sun.management.jmxremote.ssl=false"
