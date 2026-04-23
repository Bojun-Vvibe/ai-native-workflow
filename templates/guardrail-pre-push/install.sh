#!/usr/bin/env bash
# Install pre-push.sh into a target git repo's .git/hooks/.
#
# Usage:
#   ./install.sh /path/to/target/repo

set -euo pipefail

target="${1:-}"
if [ -z "$target" ]; then
  echo "usage: $0 /path/to/target/repo" >&2
  exit 2
fi

if [ ! -d "$target/.git" ]; then
  echo "error: $target is not a git repo (no .git/ directory)" >&2
  exit 2
fi

hook_src="$(cd "$(dirname "$0")" && pwd)/pre-push.sh"
hook_dst="$target/.git/hooks/pre-push"

if [ -e "$hook_dst" ] && [ ! -L "$hook_dst" ]; then
  echo "error: $hook_dst exists and is not a symlink. Move it aside first." >&2
  exit 2
fi

chmod +x "$hook_src"
ln -sf "$hook_src" "$hook_dst"
echo "installed: $hook_dst -> $hook_src"

# Friendly reminder about config
cfg="$HOME/.config/guardrail/guardrail.config.sh"
if [ ! -f "$cfg" ]; then
  echo
  echo "next: create $cfg from guardrail.config.example.sh"
  echo "      and edit INTERNAL_PATTERNS for your employer/codenames."
fi
