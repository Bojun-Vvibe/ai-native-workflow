#!/usr/bin/env bash
# llm-output-bird-bgp-no-md5-password-detector
# Flags BIRD `protocol bgp` blocks that declare a neighbor but no password.
set -u

usage() {
  echo "usage: $0 <bird.conf|->" >&2
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

out = []
i = 0
in_block = 0
while i < len(text):
    ch = text[i]
    nxt = text[i:i+2]
    if in_block:
        if nxt == "*/":
            out.append("  "); i += 2; in_block = 0; continue
        out.append(" " if ch != "\n" else "\n"); i += 1; continue
    if nxt == "/*":
        out.append("  "); i += 2; in_block = 1; continue
    if ch == "#":
        while i < len(text) and text[i] != "\n":
            out.append(" "); i += 1
        continue
    if nxt == "//":
        while i < len(text) and text[i] != "\n":
            out.append(" "); i += 1
        continue
    out.append(ch); i += 1
clean = "".join(out)

header_re = re.compile(r"\b(protocol|template)\s+bgp\b[^{]*\{")

# First pass: collect every bgp block with its kind, name, header,
# linked template (if "from X"), neighbor presence, password presence.
blocks = []
pos = 0
while True:
    m = header_re.search(clean, pos)
    if not m:
        break
    header_start = m.start()
    open_brace = m.end() - 1
    lineno = clean.count("\n", 0, header_start) + 1
    depth = 1
    j = open_brace + 1
    while j < len(clean) and depth > 0:
        c = clean[j]
        if c == "{": depth += 1
        elif c == "}": depth -= 1
        j += 1
    block_body = clean[open_brace + 1 : j - 1]
    header_text = clean[header_start:open_brace].strip()
    hm = re.match(r"(protocol|template)\s+bgp\s+(\S+)(?:\s+from\s+(\S+))?", header_text)
    kind = hm.group(1) if hm else "protocol"
    name = hm.group(2) if hm else "?"
    parent = hm.group(3) if hm else None
    has_neighbor = re.search(r"(?m)^\s*neighbor\b", block_body) is not None
    has_password = re.search(r"(?m)^\s*password\s+\"", block_body) is not None
    blocks.append({
        "kind": kind, "name": name, "parent": parent,
        "has_neighbor": has_neighbor, "has_password": has_password,
        "lineno": lineno, "header": header_text,
    })
    pos = j

by_name = {b["name"]: b for b in blocks}

def password_via_chain(b, seen=None):
    if seen is None: seen = set()
    if b["name"] in seen: return False
    seen.add(b["name"])
    if b["has_password"]: return True
    if b["parent"] and b["parent"] in by_name:
        return password_via_chain(by_name[b["parent"]], seen)
    return False

flagged = []
for b in blocks:
    if not b["has_neighbor"]:
        continue
    if password_via_chain(b):
        continue
    flagged.append((b["lineno"], b["header"]))

if flagged:
    for lineno, header in flagged:
        print(f"{path}:{lineno}: BGP block without password (TCP-MD5): {header}")
    sys.exit(1)
sys.exit(0)
'

printf '%s' "$raw" | python3 -c "$PY_SCRIPT"
