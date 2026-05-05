#!/usr/bin/env python3
"""
llm-output-krakend-debug-endpoint-detector

Flags KrakenD API gateway configurations that enable the debug
endpoint (`/__debug/`) and/or the echo endpoint (`/__echo/`) at the
top level. These endpoints expose:

  * `/__debug/<path>` -- echoes the full request including headers
    (Authorization, cookies, internal routing headers), the raw body,
    and any path / query params. An attacker can use it to harvest
    credentials forwarded by upstream auth proxies and to enumerate
    internal routing.
  * `/__echo/<path>` -- same as `/__debug/` but also reflects the
    upstream backend response, which can be used for SSRF
    confirmation and to mirror tokens injected by middlewares.

Both endpoints are toggled by top-level booleans in the KrakenD
service config:

    {
      "version": 3,
      "debug_endpoint": true,
      "echo_endpoint": true,
      ...
    }

KrakenD docs explicitly say "never enable these in production".
LLMs ship the misconfig because the upstream tutorial JSON snippets
turn them on for the "hello world" walk-through.

Maps to:
- CWE-489: Active Debug Code.
- CWE-200: Exposure of Sensitive Information.
- CWE-215: Insertion of Sensitive Information Into Debugging Code.

Stdlib-only. Reads JSON / YAML / Dockerfile / shell files passed on
argv (recurses into dirs).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We look for any of:

  1. JSON: a top-level key `"debug_endpoint"` or `"echo_endpoint"`
     whose value is the literal `true` (whitespace/comment tolerant).
  2. YAML: same keys with value `true` / `True` / `yes` / `on`.
  3. CLI / Dockerfile: `krakend run` / `krakend check` invocations
     with the `-d` / `--debug` / `-e` / `--echo` flag.
  4. Env vars: `KRAKEND_DEBUG_ENDPOINT=true` / `KRAKEND_ECHO_ENDPOINT=true`.

Comment-out lines (JSON `//`, YAML `#`, shell `#`) are stripped before
matching so docs-style examples that disable the flag for production
are not flagged on the disabled line.

False-positive guards:
  * A `false` / `False` / `no` / `off` / `0` value never fires.
  * A key inside a quoted JSON string value (e.g. a docs blob) is
    skipped via a JSON tokeniser pass.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Iterable, List, Tuple

_DEBUG_KEY = "debug_endpoint"
_ECHO_KEY = "echo_endpoint"

# YAML / shell-style comment stripping (single-line `#` and JSONC `//`).
_LINE_COMMENT_RE = re.compile(r"(?m)(?<!:)//[^\n]*$")


def _strip_jsonc_comments(text: str) -> str:
    # Drop `//` line comments (KrakenD's `flexible_config` accepts them).
    text = _LINE_COMMENT_RE.sub("", text)
    # Drop `/* ... */` block comments.
    out = []
    i = 0
    n = len(text)
    while i < n:
        if i + 1 < n and text[i] == "/" and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _strip_hash_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        in_s = False
        in_d = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _scan_json_like(text: str, path: str) -> List[Tuple[int, str]]:
    """Look for "<key>": true at the top level of JSON / JSONC text."""
    findings: List[Tuple[int, str]] = []
    cleaned = _strip_jsonc_comments(text)

    # Try a strict JSON parse first; if it succeeds and the top level
    # is an object, just inspect the root keys.
    try:
        obj = json.loads(cleaned)
    except (ValueError, TypeError):
        obj = None

    if isinstance(obj, dict):
        if obj.get(_DEBUG_KEY) is True:
            findings.append((1, _DEBUG_KEY))
        if obj.get(_ECHO_KEY) is True:
            findings.append((1, _ECHO_KEY))
        return findings

    # Fallback regex pass for partial / templated JSON.
    pat = re.compile(
        r'"(?P<k>debug_endpoint|echo_endpoint)"\s*:\s*true\b'
    )
    for m in pat.finditer(cleaned):
        # Map back to a line number in the *original* text by searching
        # for the same key:value pattern.
        orig_pat = re.compile(
            r'"' + re.escape(m.group("k")) + r'"\s*:\s*true\b'
        )
        om = orig_pat.search(text)
        ln = _line_of(text, om.start()) if om else 1
        findings.append((ln, m.group("k")))
    return findings


_YAML_TRUE = re.compile(
    r"^\s*(?P<k>debug_endpoint|echo_endpoint)\s*:\s*"
    r"(?P<v>true|True|TRUE|yes|Yes|YES|on|On|ON)\s*(?:#.*)?$",
    re.MULTILINE,
)


def _scan_yaml_like(text: str, path: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    nc = _strip_hash_comments(text)
    for m in _YAML_TRUE.finditer(nc):
        # Use the line in the original (comment-stripped already shares
        # line numbers with the original since we only blanked content
        # after `#`, not full lines).
        ln = _line_of(text, m.start())
        findings.append((ln, m.group("k")))
    return findings


# Allow JSON-array CMD form like ["krakend", "run", "-c", "...", "--debug"]
# by tolerating quotes/commas/whitespace between krakend and the flag.
_CLI_DEBUG = re.compile(
    r"\bkrakend\b[\"',\s][^\n]*?(?:run|check)[^\n]*?[\"',\s=](?:-d|--debug)\b"
)
_CLI_ECHO = re.compile(
    r"\bkrakend\b[\"',\s][^\n]*?(?:run|check)[^\n]*?[\"',\s=](?:-e|--echo)\b"
)
_ENV_DEBUG = re.compile(
    r"\bKRAKEND_DEBUG_ENDPOINT\s*[:=]\s*['\"]?(?:true|True|1|yes|on)\b"
)
_ENV_ECHO = re.compile(
    r"\bKRAKEND_ECHO_ENDPOINT\s*[:=]\s*['\"]?(?:true|True|1|yes|on)\b"
)


def _scan_shell_like(text: str, path: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    nc = _strip_hash_comments(text)
    for m in _CLI_DEBUG.finditer(nc):
        findings.append((_line_of(text, m.start()), "debug_endpoint (--debug flag)"))
    for m in _CLI_ECHO.finditer(nc):
        findings.append((_line_of(text, m.start()), "echo_endpoint (--echo flag)"))
    for m in _ENV_DEBUG.finditer(nc):
        findings.append((_line_of(text, m.start()), "KRAKEND_DEBUG_ENDPOINT=true"))
    for m in _ENV_ECHO.finditer(nc):
        findings.append((_line_of(text, m.start()), "KRAKEND_ECHO_ENDPOINT=true"))
    return findings


def scan_text(text: str, path: str) -> List[str]:
    out: List[str] = []
    seen = set()
    low = path.lower()

    candidates: List[Tuple[int, str]] = []
    if low.endswith((".json", ".jsonc", ".tmpl", ".tpl")):
        candidates.extend(_scan_json_like(text, path))
    if low.endswith((".yaml", ".yml", ".tmpl", ".tpl")):
        candidates.extend(_scan_yaml_like(text, path))
    # Always also pass shell / env scan -- compose YAMLs embed envs,
    # Dockerfiles use `ENV ...`, .env files use KEY=VALUE.
    candidates.extend(_scan_shell_like(text, path))

    # If the file extension didn't match either family, still try both
    # parsers (covers `krakend.cfg`, no-extension files, etc.).
    if not low.endswith((".json", ".jsonc", ".yaml", ".yml", ".tmpl", ".tpl")):
        candidates.extend(_scan_json_like(text, path))
        candidates.extend(_scan_yaml_like(text, path))

    for ln, what in candidates:
        key = (path, ln, what)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            f"{path}:{ln}: KrakenD {what} enabled at top level "
            f"(CWE-489/CWE-200/CWE-215, /__debug/ and /__echo/ leak "
            f"forwarded Authorization headers, cookies, and internal "
            f"routing metadata)"
        )
    return out


_TARGET_EXTS = (
    ".json", ".jsonc", ".yaml", ".yml", ".tmpl", ".tpl",
    ".sh", ".bash", ".service", ".env", ".env-example",
    ".envrc", ".conf", ".cfg",
)
_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "krakend.cfg",
    "krakend.json",
    "krakend.yaml",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
