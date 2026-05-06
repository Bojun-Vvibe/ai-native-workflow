#!/usr/bin/env bash
# Boot the Tyk gateway with the demo secret.
export TYK_GW_SECRET=tyk-gw
export TYK_GW_NODE_SECRET=secret
exec /opt/tyk-gateway/tyk --conf=/opt/tyk-gateway/tyk.conf
