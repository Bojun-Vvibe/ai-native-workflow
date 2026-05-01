#!/usr/bin/env python3
"""Detect Elasticsearch / OpenSearch configs that disable the built-in
security stack (auth, TLS, audit) on a node that is not pinned to
loopback.

Insecure shapes flagged:
  * `xpack.security.enabled: false`
  * `xpack.security.transport.ssl.enabled: false`
  * `xpack.security.http.ssl.enabled: false`
  * `plugins.security.disabled: true`            (OpenSearch security plugin)
  * `plugins.security.ssl.http.enabled: false`
  * Anonymous auth turned on with role `superuser` /
    `all_access` / `kibana_admin`.
  * Any of the above when `network.host` / `http.host` is `0.0.0.0`,
    `::`, `_site_`, `_global_`, or any non-loopback literal.

A file with a comment containing `es-no-security-allowed` anywhere is
treated as suppressed.

Exit code = number of distinct findings (0 = clean).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable

LOOPBACK_HOSTS = {
    "127.0.0.1",
    "localhost",
    "::1",
    "_local_",
}

EXPOSED_HOST_TOKENS = (
    "0.0.0.0",
    "::",
    "_site_",
    "_global_",
    "_non_loopback_",
)

SUPPRESS_MARK = "es-no-security-allowed"


def _strip_inline_comment(line: str) -> str:
    # YAML uses `#` for comments. Strip a trailing `# ...` while keeping
    # quoted values intact (good enough for config-file lint).
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _yaml_scalar(line: str) -> str | None:
    line = _strip_inline_comment(line).strip()
    if ":" not in line:
        return None
    _, _, raw = line.partition(":")
    raw = raw.strip()
    if not raw:
        return None
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        raw = raw[1:-1]
    return raw


def _flatten_yaml_keys(text: str) -> dict[str, str]:
    """Very small YAML-ish flattener.

    Supports two shapes that appear in elasticsearch.yml in the wild:

      a) flat dotted keys:           xpack.security.enabled: false
      b) nested mapping blocks:      xpack:
                                       security:
                                         enabled: false

    Returns a dict of dotted-key -> string-value (last-write-wins).
    """
    out: dict[str, str] = {}
    stack: list[tuple[int, str]] = []  # (indent, key_segment)
    for raw_line in text.splitlines():
        line = _strip_inline_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        # Pop deeper / equal indents so we sit at parent level.
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if value == "":
            stack.append((indent, key))
            continue
        # Strip surrounding quotes.
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        full_key = ".".join(seg for _, seg in stack + [(indent, key)])
        out[full_key] = value
    return out


def _is_exposed_host(value: str) -> bool:
    v = value.strip().strip('"').strip("'").lower()
    if not v:
        return False
    if v in LOOPBACK_HOSTS:
        return False
    if v in EXPOSED_HOST_TOKENS:
        return True
    # A literal IP that isn't loopback counts as exposed.
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", v) and not v.startswith("127."):
        return True
    # Hostnames other than localhost are also exposed in this lint.
    if not v.startswith("127.") and v != "localhost":
        return True
    return False


def _falseish(value: str) -> bool:
    return value.strip().strip('"').strip("'").lower() in {"false", "no", "off", "0"}


def _trueish(value: str) -> bool:
    return value.strip().strip('"').strip("'").lower() in {"true", "yes", "on", "1"}


SECURITY_OFF_KEYS = (
    "xpack.security.enabled",
    "xpack.security.transport.ssl.enabled",
    "xpack.security.http.ssl.enabled",
    "plugins.security.ssl.http.enabled",
)


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []
    flat = _flatten_yaml_keys(text)

    host = (
        flat.get("network.host")
        or flat.get("http.host")
        or flat.get("transport.host")
        or ""
    )
    exposed = _is_exposed_host(host) if host else False

    for key in SECURITY_OFF_KEYS:
        v = flat.get(key)
        if v is not None and _falseish(v):
            findings.append(f"{path}: {key}={v} (security disabled)")

    plugin_disabled = flat.get("plugins.security.disabled")
    if plugin_disabled is not None and _trueish(plugin_disabled):
        findings.append(
            f"{path}: plugins.security.disabled={plugin_disabled} "
            f"(OpenSearch security plugin disabled)"
        )

    anon_enabled = flat.get("xpack.security.authc.anonymous.roles")
    if anon_enabled:
        roles = anon_enabled.lower()
        for risky in ("superuser", "all_access", "kibana_admin"):
            if risky in roles:
                findings.append(
                    f"{path}: anonymous role grants '{risky}'"
                )

    if exposed and findings:
        findings.append(
            f"{path}: TRIFECTA security-off + host={host} (exposed) — "
            f"any client on the network can administer this cluster"
        )

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [file ...]", file=sys.stderr)
        return 2
    files: list[str] = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                for name in names:
                    if name.endswith((".yml", ".yaml", ".conf")):
                        files.append(os.path.join(root, name))
        else:
            files.append(arg)

    total = 0
    for f in files:
        for finding in scan_file(f):
            print(finding)
            total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
