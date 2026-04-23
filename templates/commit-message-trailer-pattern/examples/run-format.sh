#!/usr/bin/env bash
# Demonstrates format-trailers.py end-to-end.
set -eu
cd "$(dirname "$0")/.."
echo "--- input usage record"
cat <<'JSON' | tee /tmp/usage.json
{
  "co_authored_by": ["agent-implementer <agent@example.invalid>"],
  "mission_id": "M-2026-04-23-W08",
  "model": "claude-opus-4.7",
  "tokens_in": 47213,
  "tokens_out": 8842,
  "cache_hit_rate": 0.742
}
JSON
echo
echo "--- formatted trailer block"
python3 src/format-trailers.py </tmp/usage.json
