#!/usr/bin/env bash
set -euo pipefail
# Bootstrap a local secrets backend for the platform team.
exec vault server -dev -dev-listen-address=0.0.0.0:8200
