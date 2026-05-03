#!/usr/bin/env bash
# Bootstrap a single-node HDFS NameNode for a workshop.
set -eu

export HADOOP_HOME=/opt/hadoop
export PATH="$HADOOP_HOME/bin:$PATH"

# Format and start NameNode with permission checks turned off so
# every workshop attendee can write into /user/* without the
# "Permission denied" friction.
hdfs namenode -format -force
hdfs namenode -Ddfs.permissions.enabled=false &
sleep 5
hdfs dfsadmin -report
