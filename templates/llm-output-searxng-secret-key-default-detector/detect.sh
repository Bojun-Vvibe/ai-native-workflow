#!/usr/bin/env bash
# llm-output-searxng-secret-key-default-detector
# Flags SearXNG configs that ship the documented default / placeholder
# secret key (e.g. "ultrasecretkey", "changeme", empty, "xxxx...").
set -u

usage() {
  echo "usage: $0 <settings.yml|->" >&2
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

DEFAULTS = {
    "ultrasecretkey",
    "changeme",
    "change_me",
    "change-me",
    "please_change_me",
    "please-change-me",
    "secret",
    "replaceme",
    "replace_me",
    "replace-me",
    "default",
    "",
}

def strip_comment(line: str) -> str:
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

def normalize(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'\''"):
        v = v[1:-1]
    return v.strip()

def is_default(v: str) -> bool:
    nv = normalize(v).lower()
    if nv in DEFAULTS:
        return True
    # repeated single-character placeholders like xxxxxxxx, 00000000, aaaaaaaa
    if len(nv) >= 4 and len(set(nv)) == 1 and nv[0] in "x0a":
        return True
    return False

# YAML key form: secret_key: "ultrasecretkey"
yaml_re = re.compile(r"^\s*-?\s*secret_key\s*:\s*(.*?)\s*$")

# Env / compose forms
env_eq_re = re.compile(
    r"^\s*-?\s*(?:export\s+)?(SEARXNG_SECRET(?:_KEY)?)\s*=\s*(.*?)\s*$"
)
env_map_re = re.compile(
    r"^\s*(SEARXNG_SECRET(?:_KEY)?)\s*:\s*(.*?)\s*$"
)

flagged = []
in_server_block = False
server_indent = -1

lines = text.splitlines()
for idx, raw_line in enumerate(lines, start=1):
    line = strip_comment(raw_line)
    if not line.strip():
        continue

    # Track whether we are under a top-level `server:` mapping in YAML.
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    if re.match(r"^server\s*:\s*$", stripped):
        in_server_block = True
        server_indent = indent
        continue
    if in_server_block and indent <= server_indent and stripped and not stripped.startswith("#"):
        # Left the server: block.
        in_server_block = False
        server_indent = -1

    # YAML secret_key match — accept it whether or not we are under server:,
    # because tutorial snippets often hoist the key to the top.
    m = yaml_re.match(line)
    if m and is_default(m.group(1)):
        flagged.append((idx, "secret_key", raw_line.strip()))
        continue

    m = env_eq_re.match(line)
    if m and is_default(m.group(2)):
        flagged.append((idx, m.group(1), raw_line.strip()))
        continue

    m = env_map_re.match(line)
    if m and is_default(m.group(2)):
        flagged.append((idx, m.group(1), raw_line.strip()))
        continue

if flagged:
    for lineno, label, snippet in flagged:
        print(f"{path}:{lineno}: SearXNG {label} is a default/placeholder value: {snippet}")
    sys.exit(1)
sys.exit(0)
'

printf '%s' "$raw" | python3 -c "$PY_SCRIPT"
