#!/usr/bin/env python3
"""Detect Elasticsearch ``elasticsearch.yml`` configurations that
enable HTTP CORS with a wildcard origin allow-list.

Elasticsearch's HTTP layer ships CORS disabled by default. When an
operator enables it (``http.cors.enabled: true``) and pairs that with
``http.cors.allow-origin: "*"`` (or the regex equivalent ``/.*/``),
any origin in any browser tab can issue authenticated cross-origin
requests against the cluster's HTTP API. If
``http.cors.allow-credentials: true`` is also set, browser cookies
and HTTP auth headers are attached, turning a single visit to a
malicious page into a full read/write of the cluster (CWE-942 /
CWE-346).

LLM-generated ``elasticsearch.yml`` files routinely emit shapes like:

    http.cors.enabled: true
    http.cors.allow-origin: "*"
    http.cors.allow-credentials: true

or:

    http.cors.enabled: true
    http.cors.allow-origin: /.*/

This detector parses each YAML key/value (flat dotted form, the only
form Elasticsearch accepts for ``http.cors.*``) and flags any file
where ``http.cors.enabled`` is true and ``http.cors.allow-origin``
is a wildcard (``*``, ``/.*/``, or the unquoted form).

What's checked (per file):
  - ``http.cors.enabled: true`` is present.
  - ``http.cors.allow-origin`` is one of the wildcard shapes.
  - ``http.cors.allow-credentials: true`` escalates the message.
  - Both quoted (``"*"``) and unquoted forms are detected.

Accepted (not flagged):
  - ``http.cors.enabled: false`` (or unset).
  - ``http.cors.allow-origin`` set to a concrete origin list, e.g.
    ``https://kibana.internal``.
  - Files containing the comment ``# es-cors-wildcard-allowed``
    are skipped wholesale (intentional public dev clusters).
  - Files with no ``http.cors.*`` keys at all.

CWE refs:
  - CWE-942: Permissive Cross-domain Policy with Untrusted Domains
  - CWE-346: Origin Validation Error
  - CWE-352: Cross-Site Request Forgery (downstream impact)

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*es-cors-wildcard-allowed", re.IGNORECASE)

# Match flat "http.cors.<key>: <value>" lines. Elasticsearch accepts
# both flat dotted and nested YAML, but the dotted form dominates in
# the wild and in LLM output. We also handle the simple nested case
# below by reconstructing the dotted key.
KV_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9._-]+)\s*:\s*(?P<value>.*?)\s*(?:#.*)?$"
)

WILDCARD_VALUES = {"*", '"*"', "'*'", "/.*/", '"/.*/"', "'/.*/'"}
TRUE_VALUES = {"true", '"true"', "'true'", "yes", "on"}


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _strip(value: str) -> str:
    return value.strip()


def _flatten_yaml(source: str) -> List[Tuple[int, str, str]]:
    """Return list of (line_number, dotted_key, value).

    Handles two shapes:
      1. Flat: ``http.cors.enabled: true``
      2. Nested:
            http:
              cors:
                enabled: true

    Indent-based nesting is reconstructed by tracking a stack of
    (indent, key) pairs. Mixed-tab files are conservatively ignored
    for nested form (flat form still works).
    """
    out: List[Tuple[int, str, str]] = []
    stack: List[Tuple[int, str]] = []  # (indent_width, key)

    for i, raw in enumerate(source.splitlines(), start=1):
        if not raw.strip() or _is_comment(raw):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            # Tabs in indent: skip nesting reconstruction safely.
            continue
        m = KV_RE.match(raw)
        if not m:
            continue
        indent = len(m.group("indent"))
        key = m.group("key")
        value = _strip(m.group("value"))

        # Pop stack entries with indent >= current.
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if value == "":
            # Pure parent node (e.g. "http:") — push and continue.
            stack.append((indent, key))
            continue

        full_key = ".".join([k for _, k in stack] + [key])
        out.append((i, full_key, value))

    return out


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    pairs = _flatten_yaml(source)
    if not pairs:
        return findings

    enabled_line = 0
    enabled = False
    origin_line = 0
    origin_value = ""
    creds = False
    creds_line = 0

    for line, key, value in pairs:
        lkey = key.lower()
        if lkey == "http.cors.enabled":
            enabled_line = line
            enabled = value.lower() in TRUE_VALUES
        elif lkey == "http.cors.allow-origin":
            origin_line = line
            origin_value = value
        elif lkey == "http.cors.allow-credentials":
            creds_line = line
            creds = value.lower() in TRUE_VALUES

    if not enabled:
        return findings

    if origin_value in WILDCARD_VALUES:
        report_line = origin_line or enabled_line
        extra = ""
        if creds:
            extra = (
                f" (escalated: http.cors.allow-credentials=true at "
                f"line {creds_line})"
            )
        findings.append(
            (
                report_line,
                "elasticsearch http.cors.allow-origin is a wildcard "
                f"({origin_value!r}) with http.cors.enabled=true"
                + extra,
            )
        )

    return findings


def _is_es_yml(path: Path) -> bool:
    name = path.name.lower()
    if name == "elasticsearch.yml" or name == "elasticsearch.yaml":
        return True
    if name.endswith((".yml", ".yaml")) and "elasticsearch" in name:
        return True
    # Fixture filenames in examples/ tend to contain "elasticsearch".
    if name.endswith((".yml", ".yaml")) and "es-" in name:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_es_yml(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
