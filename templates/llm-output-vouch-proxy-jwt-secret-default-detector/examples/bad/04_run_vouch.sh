#!/usr/bin/env bash
# quick start vouch-proxy
export VOUCH_OAUTH_PROVIDER=github
export VOUCH_JWT_SECRET=secret
exec /usr/local/bin/vouch-proxy -config /etc/vouch/config.yml
