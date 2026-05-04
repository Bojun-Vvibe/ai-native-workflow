#!/usr/bin/env python3
"""Detect Adminer deployment configurations from LLM output where
the login form is left unrestricted (any database server hostname
accepted) and the container is exposed beyond localhost.

Adminer ships as a single PHP file. Out of the box, the login form
accepts an arbitrary ``server`` value, which means anyone who can
reach the Adminer URL can use it as a database client / port
scanner against any host the Adminer container can route to. This
is well documented (https://www.adminer.org/en/plugins/) and the
upstream guidance is to either:

  - run a customised ``index.php`` that constructs the
    ``Adminer`` instance with ``AdminerLoginServers`` /
    ``AdminerLoginPasswordLess`` / ``AdminerRestrictAccess``, or
  - bind Adminer to the loopback interface and front it with an
    auth-enforcing reverse proxy.

LLMs that copy the upstream "minimal" docker-compose example
verbatim almost never wire up a plugin, and they tend to publish
the Adminer port directly on ``0.0.0.0`` ``8080``. The result is
an unauthenticated DB pivot host on the public internet.

This detector flags four orthogonal regressions on configs that
are clearly Adminer (mention the ``adminer`` image, the
``adminer.php`` file, or the ``ADMINER_*`` env keys):

  1. The Adminer port is published on a non-loopback host (compose
     ``ports:`` entry such as ``"8080:8080"``, ``"0.0.0.0:8080:..."``,
     or any explicit non-loopback bind) AND no plugin / restriction
     marker is present.
  2. ``ADMINER_DEFAULT_SERVER`` is unset on a publicly-exposed
     deployment (default behaviour: free-form server field).
  3. A custom ``index.php`` is referenced but it does not include
     any ``AdminerLoginServers`` / ``AdminerRestrictAccess`` /
     ``AdminerLoginPasswordLess`` / ``AdminerLoginIp`` token.
  4. ``ADMINER_PLUGINS`` is set but does not include any of the
     access-restriction plugins (``login-servers``,
     ``login-password-less``, ``restrict-access``, ``login-ip``).

Suppression: a top-level ``# adminer-server-restriction-ok``
comment in the file disables all rules (use only when an external
auth layer such as forward-auth via Traefik / nginx / oauth2-proxy
is enforced).

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-918 (Server-Side Request Forgery — Adminer can be coerced to
connect to arbitrary internal hosts),
CWE-1188 (Insecure Default Initialization of Resource).

Public API:
    scan(text: str) -> list[tuple[int, str]]
        Returns a list of (line_number_1based, reason) tuples.
        Empty list = clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*adminer-server-restriction-ok", re.IGNORECASE)

# Adminer deployment markers — any one of these is enough to make
# the file in scope.
ADMINER_MARKERS = [
    re.compile(r"(?im)^\s*image\s*:\s*[\"']?adminer(?::|[\"']|\s|$)"),
    re.compile(r"(?im)^\s*image\s*:\s*[\"']?dockware/adminer"),
    re.compile(r"\badminer\.php\b", re.IGNORECASE),
    re.compile(r"(?ix)(?:^|[\s,;])(?:export\s+)?ADMINER_[A-Z0-9_]+[ \t]*[:=]"),
]

# Restriction plugin / API tokens — presence of any of these in
# the same blob suppresses the "no restriction" findings.
RESTRICTION_TOKENS = [
    re.compile(r"\bAdminerLoginServers\b"),
    re.compile(r"\bAdminerRestrictAccess\b"),
    re.compile(r"\bAdminerLoginPasswordLess\b"),
    re.compile(r"\bAdminerLoginIp\b"),
    re.compile(r"\blogin-servers\b"),
    re.compile(r"\brestrict-access\b"),
    re.compile(r"\blogin-password-less\b"),
    re.compile(r"\blogin-ip\b"),
]

# A "ports:" entry that publishes Adminer on a non-loopback
# interface. Matches:
#   - "8080:8080"
#   - "0.0.0.0:8080:8080"
#   - "10.0.0.5:8080:8080"
#   - 8080:8080 (unquoted)
# Excludes:
#   - "127.0.0.1:8080:8080"
#   - "localhost:8080:8080"
PORT_LINE = re.compile(
    r"""(?ix)
    ^\s*-?\s*[\"']?
    (?:(?P<bind>\d{1,3}(?:\.\d{1,3}){3}|localhost|::1):)?
    (?P<host>\d{2,5})
    :
    (?P<container>\d{2,5})
    (?:/(?:tcp|udp))?
    [\"']?\s*$
    """,
    re.MULTILINE,
)

# Custom index.php reference (volume mount or COPY).
CUSTOM_INDEX = re.compile(
    r"""(?ix)
    (?:
        :\s*/var/www/html/index\.php
        |
        (?:^|\s)COPY\s+\S*index\.php\s+/var/www/html/
        |
        (?:^|\s)ADD\s+\S*index\.php\s+/var/www/html/
    )
    """,
)

ADMINER_DEFAULT_SERVER = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?
    ADMINER_DEFAULT_SERVER
    [ \t]*[:=][ \t]*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)

ADMINER_PLUGINS = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?
    ADMINER_PLUGINS
    [ \t]*[:=][ \t]*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;\n]*)
    """,
)

LOCAL_BINDS = {"127.0.0.1", "127.0.0.0", "localhost", "::1"}


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _is_adminer_config(text: str) -> bool:
    for m in ADMINER_MARKERS:
        if m.search(text):
            return True
    return False


def _has_restriction_token(text: str) -> bool:
    for m in RESTRICTION_TOKENS:
        if m.search(text):
            return True
    return False


def _public_port_lines(text: str) -> List[Tuple[int, str]]:
    """Return (line_number, raw_match) for each ports: entry that
    publishes a non-loopback bind in the typical Adminer range
    (3000-9999)."""
    out: List[Tuple[int, str]] = []
    # Find the "ports:" section and inspect entries underneath. We
    # take a simple approach: scan every line; if it looks like a
    # ports entry and matches PORT_LINE, classify it.
    in_ports = False
    base_indent = -1
    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        # Detect a "ports:" key.
        m_ports = re.match(r"^(\s*)ports\s*:\s*$", raw)
        if m_ports:
            in_ports = True
            base_indent = len(m_ports.group(1))
            continue
        if in_ports:
            indent = len(raw) - len(raw.lstrip())
            if indent <= base_indent and stripped and not stripped.startswith("#"):
                in_ports = False
            else:
                m = PORT_LINE.match(raw)
                if m:
                    bind = (m.group("bind") or "").strip().lower()
                    host = m.group("host")
                    if bind in LOCAL_BINDS:
                        continue
                    # Heuristic: only flag if host port is in a
                    # plausible web range (3000-9999) to avoid
                    # noise from unrelated services.
                    try:
                        h = int(host)
                    except ValueError:
                        continue
                    if 3000 <= h <= 9999:
                        out.append((i, raw.strip()))
    return out


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    if not _is_adminer_config(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []

    has_restriction = _has_restriction_token(text)

    # Plugin env handling: ADMINER_PLUGINS is the official knob.
    plugins_match = ADMINER_PLUGINS.search(text)
    plugin_value = _strip(plugins_match.group("val")) if plugins_match else ""
    plugin_names = re.split(r"[\s,]+", plugin_value) if plugin_value else []
    plugin_has_restriction = any(
        p in {"login-servers", "restrict-access", "login-password-less", "login-ip"}
        for p in plugin_names
    )

    # Rule 4: ADMINER_PLUGINS set but no restriction plugin in it.
    if plugins_match is not None and not plugin_has_restriction and not has_restriction:
        line_no = 1
        for i, ln in enumerate(lines, start=1):
            if "ADMINER_PLUGINS" in ln:
                line_no = i
                break
        findings.append(
            (
                line_no,
                "ADMINER_PLUGINS set but contains no access-restriction plugin "
                "(expected one of: login-servers, restrict-access, "
                "login-password-less, login-ip)",
            )
        )

    # Rule 3: custom index.php referenced but no restriction token
    # appears anywhere in the blob (including the index.php itself
    # if it was inlined).
    if CUSTOM_INDEX.search(text) and not has_restriction and not plugin_has_restriction:
        line_no = 1
        for i, ln in enumerate(lines, start=1):
            if "/var/www/html/index.php" in ln or re.search(r"\bindex\.php\b", ln):
                line_no = i
                break
        findings.append(
            (
                line_no,
                "Custom Adminer index.php is referenced but the file does not call "
                "AdminerLoginServers / AdminerRestrictAccess / "
                "AdminerLoginPasswordLess / AdminerLoginIp",
            )
        )

    # Rule 1: publicly published port with no restriction in the
    # whole config.
    public_ports = _public_port_lines(text)
    if public_ports and not has_restriction and not plugin_has_restriction:
        line_no, raw = public_ports[0]
        findings.append(
            (
                line_no,
                "Adminer is published beyond loopback ("
                + raw
                + ") with no server-restriction plugin; the login form will accept "
                "any database hostname the container can route to (DB pivot / SSRF)",
            )
        )

    # Rule 2: ADMINER_DEFAULT_SERVER unset on a publicly-exposed
    # deployment. We only fire this if the publish-port rule did
    # not already fire for the same config (the message would be
    # redundant), and there is no plugin restriction.
    if (
        public_ports
        and ADMINER_DEFAULT_SERVER.search(text) is None
        and not has_restriction
        and not plugin_has_restriction
        and not findings  # avoid duplicate noise on the same root cause
    ):
        line_no, _ = public_ports[0]
        findings.append(
            (
                line_no,
                "ADMINER_DEFAULT_SERVER is not set on a publicly-exposed Adminer "
                "deployment; the login form is free-form by default",
            )
        )

    return findings


def _scan_path(p: Path) -> int:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{p}:0:read-error: {exc}")
        return 0
    hits = scan(text)
    for line, reason in hits:
        print(f"{p}:{line}:{reason}")
    return 1 if hits else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    n = 0
    for a in argv[1:]:
        n += _scan_path(Path(a))
    return min(255, n)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
