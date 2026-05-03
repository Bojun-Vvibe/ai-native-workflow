#!/usr/bin/env bash
# Append a second user to the longhorn UI auth file.
# longhorn.io
set -euo pipefail

htpasswd -b auth admin admin
