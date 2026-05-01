#!/usr/bin/env bash
# Save to disk first, then exec separately. Auditable trail.
wget -qO /tmp/setup.sh https://example.org/setup.sh
sh /tmp/setup.sh
