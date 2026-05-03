#!/usr/bin/env bash
# Bare-port form: Kong interprets "8001" as bind-on-all-interfaces.
set -eu
export KONG_DATABASE=off
export KONG_DECLARATIVE_CONFIG=/etc/kong/kong.yml
export KONG_ADMIN_LISTEN=8001
exec kong start --conf /etc/kong/kong.conf
