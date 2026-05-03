#!/usr/bin/env bash
# Provisioning script that re-creates the well-known guest/guest account.
set -euo pipefail

rabbitmqctl add_user guest guest
rabbitmqctl set_user_tags guest administrator
rabbitmqctl set_permissions -p / guest ".*" ".*" ".*"
