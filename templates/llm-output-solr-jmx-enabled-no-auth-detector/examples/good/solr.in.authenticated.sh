#!/bin/bash
SOLR_HEAP="2g"
ENABLE_REMOTE_JMX_OPTS="true"
RMI_PORT="18983"
SOLR_OPTS="$SOLR_OPTS -Dcom.sun.management.jmxremote.authenticate=true"
SOLR_OPTS="$SOLR_OPTS -Dcom.sun.management.jmxremote.password.file=/etc/solr/jmx.pwd"
SOLR_OPTS="$SOLR_OPTS -Dcom.sun.management.jmxremote.access.file=/etc/solr/jmx.access"
