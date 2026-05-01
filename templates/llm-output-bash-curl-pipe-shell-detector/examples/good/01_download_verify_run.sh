#!/usr/bin/env bash
set -euo pipefail
# Download to disk, verify checksum, then run. Auditable.
curl -fsSL -o /tmp/install.sh https://get.example.com/install.sh
echo "abc123  /tmp/install.sh" | sha256sum -c -
bash /tmp/install.sh
