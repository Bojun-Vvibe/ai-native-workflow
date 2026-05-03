#!/usr/bin/env bash
# Start NameNode with permission checks ENABLED (default).
# Fix the underlying directory owner with -chown rather than
# disabling dfs.permissions.enabled.
set -eu

export HADOOP_HOME=/opt/hadoop
export PATH="$HADOOP_HOME/bin:$PATH"

hdfs namenode -format -force
hdfs --daemon start namenode
sleep 5
hdfs dfs -mkdir -p /user/analyst
hdfs dfs -chown analyst:analysts /user/analyst
hdfs dfs -chmod 0750 /user/analyst
