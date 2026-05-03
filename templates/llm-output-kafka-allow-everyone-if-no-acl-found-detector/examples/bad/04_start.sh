#!/usr/bin/env bash
# Bad: ships the dangerous JVM property via KAFKA_OPTS
export KAFKA_OPTS="-Djava.security.auth.login.config=/etc/kafka/jaas.conf -Dallow.everyone.if.no.acl.found=true"
exec /opt/kafka/bin/kafka-server-start.sh /etc/kafka/server.properties
