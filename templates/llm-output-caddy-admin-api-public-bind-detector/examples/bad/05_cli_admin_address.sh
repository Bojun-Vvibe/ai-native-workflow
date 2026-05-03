#!/usr/bin/env bash
# spin up caddy with admin reachable from CI runner
caddy run --config /etc/caddy/Caddyfile --admin --address 0.0.0.0:2019
