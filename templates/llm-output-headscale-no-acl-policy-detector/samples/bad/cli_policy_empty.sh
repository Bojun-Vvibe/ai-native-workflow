#!/usr/bin/env bash
# Bad: launching headscale with the policy explicitly cleared on the
# command line — every successfully-registered node can reach every
# other node on every port.
exec headscale serve --config /etc/headscale/config.yaml --policy ""
