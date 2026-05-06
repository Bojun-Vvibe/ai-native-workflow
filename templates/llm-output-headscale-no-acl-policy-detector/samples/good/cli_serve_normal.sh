#!/usr/bin/env bash
# Good: launching headscale with a real config that wires in the
# ACL file. No --policy override.
exec headscale serve --config /etc/headscale/config.yaml
