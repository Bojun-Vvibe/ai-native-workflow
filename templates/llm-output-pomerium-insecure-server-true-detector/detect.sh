#!/usr/bin/env bash
# llm-output-pomerium-insecure-server-true-detector
# Flags Pomerium configs that disable TLS on the data plane via
# insecure_server: true (YAML) or POMERIUM_INSECURE_SERVER=true (env).
set -u

usage() {
  echo "usage: $0 <config.yaml|->" >&2
  exit 2
}

[ $# -eq 1 ] || usage
src="$1"

if [ "$src" = "-" ]; then
  display_path="<stdin>"
  raw="$(cat)"
else
  [ -r "$src" ] || { echo "cannot read: $src" >&2; exit 2; }
  display_path="$src"
  raw="$(cat "$src")"
fi

export DISPLAY_PATH="$display_path"

PY_SCRIPT='
import os, re, sys

path = os.environ.get("DISPLAY_PATH", "<stdin>")
text = sys.stdin.read()

TRUTHY = {"true", "yes", "on"}

def strip_comment(line: str) -> str:
    # Strip a trailing # comment, but only when the # is outside quotes.
    out, in_s, in_d = [], False, False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\"" and not in_s:
            in_d = not in_d
        elif ch == "'\''" and not in_d:
            in_s = not in_s
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)

def is_truthy(v: str) -> bool:
    v = v.strip()
    if not v:
        return False
    # strip matched surrounding quotes
    if (v[0] == v[-1]) and v[0] in ("\"", "'\''") and len(v) >= 2:
        v = v[1:-1]
    return v.strip().lower() in TRUTHY

# YAML key form:  insecure_server: true   (with optional leading "- " for list-of-maps)
yaml_re = re.compile(r"^\s*-?\s*insecure_server\s*:\s*(.+?)\s*$")

# env / compose-list form:
#   POMERIUM_INSECURE_SERVER=true
#   export POMERIUM_INSECURE_SERVER="true"
#   - POMERIUM_INSECURE_SERVER=true
env_eq_re = re.compile(
    r"^\s*-?\s*(?:export\s+)?POMERIUM_INSECURE_SERVER\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)

# compose env-map form:  POMERIUM_INSECURE_SERVER: "true"
env_map_re = re.compile(
    r"^\s*POMERIUM_INSECURE_SERVER\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

flagged = []
for idx, raw_line in enumerate(text.splitlines(), start=1):
    line = strip_comment(raw_line)
    if not line.strip():
        continue
    for rgx, label in (
        (yaml_re,    "insecure_server"),
        (env_eq_re,  "POMERIUM_INSECURE_SERVER"),
        (env_map_re, "POMERIUM_INSECURE_SERVER"),
    ):
        m = rgx.match(line)
        if m and is_truthy(m.group(1)):
            flagged.append((idx, label, raw_line.strip()))
            break

if flagged:
    for lineno, label, snippet in flagged:
        print(f"{path}:{lineno}: Pomerium {label} enabled (TLS disabled): {snippet}")
    sys.exit(1)
sys.exit(0)
'

printf '%s' "$raw" | python3 -c "$PY_SCRIPT"
