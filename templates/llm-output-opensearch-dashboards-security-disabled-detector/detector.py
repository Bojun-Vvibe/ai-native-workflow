#!/usr/bin/env python3
"""Detect OpenSearch Dashboards ``opensearch_dashboards.yml`` files that
disable the Security plugin's UI multitenancy / authentication layer
while still pointing at a non-loopback OpenSearch cluster.

This is the Dashboards-side counterpart to disabling the Security plugin
on the OpenSearch cluster: even when the cluster itself runs with
Security enabled, a Dashboards instance configured with
``opensearch_security.disabled: true`` (or
``opensearch_security.auth.type: ""`` paired with no SAML/OIDC/Basic
config, or ``opensearch_security.multitenancy.enabled: false`` plus
``opensearch.username: kibanaserver`` / ``admin`` reuse) leaves the UI
wide open: any browser hitting :5601 lands directly on a session
authenticated as the static service account.

What this detector flags
------------------------

A file is flagged when **any** of the following hold and the Dashboards
binding is not loopback-only:

* ``opensearch_security.disabled: true`` is present (top-level switch
  shipped by the Security plugin).
* ``opensearch_security.auth.type`` is set to an empty string, ``""``,
  ``[]``, or ``"none"`` while no other auth backend keys
  (``opensearch_security.openid.*``, ``opensearch_security.saml.*``,
  ``opensearch_security.proxycache.*``,
  ``opensearch_security.basicauth.*``) are configured.
* ``opensearch.username`` is the well-known service account
  (``kibanaserver``, ``admin``, ``opensearch_dashboards_user``) AND
  ``opensearch.password`` is one of the shipped defaults
  (``kibanaserver``, ``admin``, ``changeme``).
* ``server.ssl.enabled`` is ``false`` while ``server.host`` is bound on
  a non-loopback interface (``0.0.0.0``, ``::``, or a public IP/host).

A file is *good* when:

* ``server.host`` is loopback (``127.0.0.1``, ``::1``, ``localhost``)
  AND no other rule fires, OR
* The Security plugin is enabled with a configured auth backend, OR
* The line carries the suppression marker
  ``# osd-security-disabled-allowed``.

The detector is regex/line based — no YAML parser. It tolerates inline
comments and quoted/unquoted scalars.

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*osd-security-disabled-allowed\b")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}
PUBLIC_BIND = {"0.0.0.0", "::", "*"}

DEFAULT_SERVICE_USERS = {"kibanaserver", "admin", "opensearch_dashboards_user"}
DEFAULT_PASSWORDS = {"kibanaserver", "admin", "changeme", "password"}

KEY_RE = re.compile(
    r"""^(?P<indent>\s*)
        (?P<key>[A-Za-z0-9_.\-]+)
        \s*:\s*
        (?P<value>.*?)
        \s*(?:\#.*)?$
    """,
    re.VERBOSE,
)

QUOTE_RE = re.compile(r"""^(['"])(.*)\1$""")


def _strip_value(raw: str) -> str:
    v = raw.strip()
    m = QUOTE_RE.match(v)
    if m:
        return m.group(2).strip()
    return v


def _parse(source: str) -> Tuple[Dict[str, Tuple[int, str]], List[str]]:
    """Return ({key: (lineno, value)}, raw_lines)."""
    data: Dict[str, Tuple[int, str]] = {}
    lines = source.splitlines()
    for i, raw in enumerate(lines, 1):
        if SUPPRESS.search(raw):
            continue
        # skip list items / nested-only lines
        m = KEY_RE.match(raw)
        if not m:
            continue
        key = m.group("key")
        # We only care about top-level dotted keys used by Dashboards.
        if "." not in key and key not in {
            "server",
            "opensearch",
            "opensearch_security",
        }:
            # plain top-level scalars (e.g. server.host alt form) still ok
            pass
        value = _strip_value(m.group("value"))
        data[key] = (i, value)
    return data, lines


def _bind_is_remote(value: str) -> bool:
    if not value:
        return False
    v = value.strip()
    if v in LOOPBACK_HOSTS:
        return False
    if v in PUBLIC_BIND:
        return True
    # Anything else that isn't loopback we treat as remote-reachable.
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source) and source.count("\n") < 4:
        # whole-file suppression for tiny fixture files
        return findings

    data, _ = _parse(source)

    server_host_line, server_host = data.get("server.host", (0, ""))
    bind_remote = _bind_is_remote(server_host) if server_host else True
    # Default Dashboards behaviour binds to localhost, but most production
    # configs override it. We only suppress findings when host is
    # explicitly set to a loopback value.
    suppress_for_loopback = bool(server_host) and not bind_remote

    # Rule 1: explicit security.disabled = true
    sd_line, sd_val = data.get("opensearch_security.disabled", (0, ""))
    if sd_val.lower() == "true":
        if not suppress_for_loopback:
            findings.append(
                (
                    sd_line,
                    "opensearch_security.disabled is true — Security plugin"
                    " bypassed on a non-loopback Dashboards binding",
                )
            )

    # Rule 2: auth.type empty/none with no backend configured.
    at_line, at_val = data.get("opensearch_security.auth.type", (0, ""))
    if at_val.strip().lower() in {"", '""', "[]", "none", "''"} and at_line:
        backend_keys = [
            k
            for k in data
            if k.startswith("opensearch_security.openid.")
            or k.startswith("opensearch_security.saml.")
            or k.startswith("opensearch_security.proxycache.")
            or k.startswith("opensearch_security.basicauth.")
            or k.startswith("opensearch_security.jwt.")
        ]
        if not backend_keys and not suppress_for_loopback:
            findings.append(
                (
                    at_line,
                    "opensearch_security.auth.type is empty/none with no"
                    " openid/saml/jwt/proxycache/basicauth backend configured",
                )
            )

    # Rule 3: default service-account credentials reused.
    user_line, user_val = data.get("opensearch.username", (0, ""))
    pass_line, pass_val = data.get("opensearch.password", (0, ""))
    if user_val in DEFAULT_SERVICE_USERS and pass_val in DEFAULT_PASSWORDS:
        if not suppress_for_loopback:
            findings.append(
                (
                    user_line or pass_line,
                    f"opensearch.username='{user_val}' reuses the default"
                    f" service account with default password '{pass_val}'",
                )
            )

    # Rule 4: TLS off on a public binding.
    ssl_line, ssl_val = data.get("server.ssl.enabled", (0, ""))
    if ssl_val.lower() == "false" and bind_remote and server_host:
        findings.append(
            (
                ssl_line,
                f"server.ssl.enabled=false while server.host='{server_host}' is"
                " not loopback — Dashboards session cookie travels in cleartext",
            )
        )

    # de-dup
    seen = set()
    out = []
    for ln, r in findings:
        if (ln, r) in seen:
            continue
        seen.add((ln, r))
        out.append((ln, r))
    out.sort()
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("opensearch_dashboards.yml")))
            targets.extend(sorted(path.rglob("*.yml")))
            targets.extend(sorted(path.rglob("*.yaml")))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
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
