#!/usr/bin/env python3
"""Detect OpenSearch / OpenSearch Dashboards configs that disable the
bundled OpenSearch Security plugin.

OpenSearch ships with a security plugin that handles auth, TLS-on-
transport, audit logging, and RBAC. Turning it off (one line in
``opensearch.yml`` or one env var in docker-compose) leaves port 9200
open to anyone on the network, and LLMs asked for a "working
single-node OpenSearch docker-compose" tend to emit precisely that
shape because it makes the demo-cert chain stop complaining.

What's flagged
--------------
Per file (line-level):

* ``plugins.security.disabled: true``
* ``opensearch_security.disabled: true``
* ``DISABLE_SECURITY_PLUGIN=true`` (env var, compose/.env)
* ``DISABLE_SECURITY_DASHBOARDS_PLUGIN=true`` (env var)
* ``plugins.security.ssl.http.enabled: false``
* The pair ``plugins.security.allow_default_init_securityindex: true``
  + ``plugins.security.allow_unsafe_democertificates: true`` in a
  file that also binds ``network.host`` to a non-loopback address.

Per file (whole-file):

* An ``opensearch.yml`` (filename match) where ``network.host`` is
  bound to a non-loopback address AND ``plugins.security.ssl.transport.enabled``
  is not set true AND ``plugins.security.disabled`` is not set false.

What's NOT flagged
------------------
* ``plugins.security.disabled: false`` — explicit enable.
* ``network.host: 127.0.0.1`` / ``localhost`` only.
* Files containing ``# os-sec-ok-file`` anywhere.
* Lines with a trailing ``# os-sec-ok`` comment.
* Blocks bracketed by ``# os-sec-ok-begin`` / ``# os-sec-ok-end``.

Refs
----
* CWE-306: Missing Authentication for Critical Function
* CWE-1188: Insecure Default Initialization of Resource

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*os-sec-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*os-sec-ok-file\b")
SUPPRESS_BEGIN = re.compile(r"#\s*os-sec-ok-begin\b")
SUPPRESS_END = re.compile(r"#\s*os-sec-ok-end\b")

SEC_DISABLED_TRUE = re.compile(
    r"^\s*plugins\.security\.disabled\s*:\s*true\b", re.IGNORECASE
)
SEC_DISABLED_FALSE = re.compile(
    r"^\s*plugins\.security\.disabled\s*:\s*false\b", re.IGNORECASE
)
DASHBOARDS_SEC_DISABLED = re.compile(
    r"^\s*opensearch_security\.disabled\s*:\s*true\b", re.IGNORECASE
)
HTTP_TLS_OFF = re.compile(
    r"^\s*plugins\.security\.ssl\.http\.enabled\s*:\s*false\b", re.IGNORECASE
)
TRANSPORT_TLS_TRUE = re.compile(
    r"^\s*plugins\.security\.ssl\.transport\.enabled\s*:\s*true\b", re.IGNORECASE
)
ALLOW_DEMO_CERTS = re.compile(
    r"^\s*plugins\.security\.allow_unsafe_democertificates\s*:\s*true\b",
    re.IGNORECASE,
)
ALLOW_DEFAULT_INIT = re.compile(
    r"^\s*plugins\.security\.allow_default_init_securityindex\s*:\s*true\b",
    re.IGNORECASE,
)
NETWORK_HOST = re.compile(r"^\s*network\.host\s*:\s*['\"]?([^\s'\"#]+)", re.IGNORECASE)
ENV_DISABLE_SEC = re.compile(
    r"\bDISABLE_SECURITY_PLUGIN\s*[:=]\s*[\"']?true[\"']?\b", re.IGNORECASE
)
ENV_DISABLE_DASH = re.compile(
    r"\bDISABLE_SECURITY_DASHBOARDS_PLUGIN\s*[:=]\s*[\"']?true[\"']?\b",
    re.IGNORECASE,
)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "_local_"}


def _strip_comment(line: str) -> str:
    # YAML comments are # but only when not in a quoted scalar; for our
    # narrow keys this naive split is safe.
    return line.split("#", 1)[0]


def _is_loopback(addr: str) -> bool:
    return addr.strip().lower() in LOOPBACK


def scan(source: str, filename: str = "") -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    lines = source.splitlines()

    suppressed = set()
    in_fence = False
    for i, raw in enumerate(lines, start=1):
        if SUPPRESS_BEGIN.search(raw):
            in_fence = True
            suppressed.add(i)
            continue
        if SUPPRESS_END.search(raw):
            in_fence = False
            suppressed.add(i)
            continue
        if in_fence:
            suppressed.add(i)

    has_sec_disabled_false = False
    has_transport_tls_true = False
    has_nonloopback_network_host = False
    has_allow_demo_certs = False
    allow_demo_certs_line = 0
    has_allow_default_init = False

    for i, raw in enumerate(lines, start=1):
        if i in suppressed or SUPPRESS_LINE.search(raw):
            continue
        body = _strip_comment(raw)

        if SEC_DISABLED_TRUE.search(body):
            findings.append((i, "plugins.security.disabled: true turns off auth/TLS/RBAC for the whole cluster"))
            continue
        if SEC_DISABLED_FALSE.search(body):
            has_sec_disabled_false = True
            continue
        if DASHBOARDS_SEC_DISABLED.search(body):
            findings.append((i, "opensearch_security.disabled: true removes the Dashboards login screen"))
            continue
        if HTTP_TLS_OFF.search(body):
            findings.append((i, "plugins.security.ssl.http.enabled: false sends credentials in plaintext over 9200"))
            continue
        if TRANSPORT_TLS_TRUE.search(body):
            has_transport_tls_true = True
        if ALLOW_DEMO_CERTS.search(body):
            has_allow_demo_certs = True
            allow_demo_certs_line = i
        if ALLOW_DEFAULT_INIT.search(body):
            has_allow_default_init = True
        m = NETWORK_HOST.match(body)
        if m and not _is_loopback(m.group(1)):
            has_nonloopback_network_host = True
        if ENV_DISABLE_SEC.search(raw):
            findings.append((i, "DISABLE_SECURITY_PLUGIN=true env var disables OpenSearch Security"))
            continue
        if ENV_DISABLE_DASH.search(raw):
            findings.append((i, "DISABLE_SECURITY_DASHBOARDS_PLUGIN=true env var disables Dashboards auth"))
            continue

    # Demo certs + default init + non-loopback bind = production with demo certs.
    if (
        has_allow_demo_certs
        and has_allow_default_init
        and has_nonloopback_network_host
    ):
        findings.append((
            allow_demo_certs_line,
            "demo certs + allow_default_init_securityindex + non-loopback network.host: shipping demo PKI",
        ))

    # Whole-file finding for opensearch.yml only.
    base = Path(filename).name.lower()
    if base in ("opensearch.yml", "opensearch.yaml") and has_nonloopback_network_host:
        if not has_transport_tls_true and not has_sec_disabled_false:
            # avoid double-counting if we already flagged disabled: true
            already_flagged_disable = any("plugins.security.disabled: true" in r for _, r in findings)
            if not already_flagged_disable:
                findings.append((
                    0,
                    "non-loopback opensearch.yml without plugins.security.ssl.transport.enabled: true and no plugins.security.disabled: false",
                ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "opensearch.yml",
        "opensearch.yaml",
        "opensearch_dashboards.yml",
        "opensearch_dashboards.yaml",
        "docker-compose*.y*ml",
        ".env",
        "*.env",
    )
    for pattern in patterns:
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_files(root):
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            hits = scan(source, str(f))
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
