#!/usr/bin/env python3
"""Detect unquoted values containing spaces in .env style files.

Many dotenv loaders treat `KEY=foo bar` as `KEY=foo` and silently drop
" bar". LLMs that emit env files frequently miss the quoting. This
detector flags lines where:
  - the line is a KEY=VALUE assignment (not blank, not comment),
  - the value is not wrapped in matching single or double quotes,
  - the value contains at least one ASCII space or tab,
  - and the value is not an inline-comment-only suffix.

Pure stdlib. Code-fence aware: lines inside ``` fences are ignored so
the detector can be pointed at a markdown blob containing a .env block.
"""
from __future__ import annotations

import sys
from pathlib import Path

KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")


def _split_kv(line: str):
    if "=" not in line:
        return None
    key, _, rest = line.partition("=")
    key = key.strip()
    if key.startswith("export "):
        key = key[len("export "):].strip()
    if not key or any(c not in KEY_CHARS for c in key):
        return None
    return key, rest


def _value_quoted(value: str) -> bool:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return True
    return False


def detect(text: str):
    findings = []
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        kv = _split_kv(raw)
        if kv is None:
            continue
        key, rest = kv
        # Strip trailing inline comment only if value isn't quoted.
        value = rest
        if _value_quoted(value.strip()):
            continue
        # Only consider portion before a ' #' inline comment.
        cut = value
        hash_idx = cut.find(" #")
        if hash_idx != -1:
            cut = cut[:hash_idx]
        v = cut.strip()
        if not v:
            continue
        if " " in v or "\t" in v:
            findings.append(
                {
                    "line": lineno,
                    "key": key,
                    "value": v,
                    "message": f"unquoted value for {key!s} contains whitespace; "
                    "most loaders will truncate at the first space",
                }
            )
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detector.py <file>", file=sys.stderr)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    findings = detect(text)
    if not findings:
        print("OK: no unquoted-spaces findings")
        return 0
    print(f"FOUND {len(findings)} finding(s):")
    for f in findings:
        print(f"  line {f['line']}: {f['key']}={f['value']!r} -- {f['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
