#!/usr/bin/env python3
"""Detect Syncthing configurations from LLM output that leave the
GUI / REST API without authentication while binding to a non-loopback
address.

Syncthing's GUI is more than a status page: it can add / remove
shared folders, accept new device pairings, schedule rescans,
and read every file in any shared folder via the REST API. The
upstream defaults are deliberately conservative — the GUI binds
to ``127.0.0.1:8384`` and an API key must be presented for any
mutating call. LLMs that emit a "container-friendly" config
override the bind address to ``0.0.0.0`` (so the host's port
mapping works) but forget to enable the ``<gui>`` ``user`` /
``password`` pair, leaving the API open.

This detector parses ``config.xml`` blobs (and ``STGUIADDRESS`` /
``STGUIAPIKEY`` env-var snippets) and flags four orthogonal
regressions:

  1. ``<gui>`` element bound to ``0.0.0.0`` / ``::`` / a non-loopback
     IP with no ``<user>`` child.
  2. ``<gui>`` bound publicly with an empty ``<password>`` element.
  3. ``<gui>`` bound publicly with no ``<apikey>`` element (mutating
     calls require an API key on top of, or instead of, basic auth).
  4. ``STGUIADDRESS`` env-var set to ``0.0.0.0:<port>`` while
     ``STGUIAPIKEY`` is unset or empty.

The detector is intentionally generous about bind syntax: it
accepts ``0.0.0.0:8384``, ``[::]:8384``, ``http://0.0.0.0:8384``,
and bare numeric forms like ``0.0.0.0``. Loopback values (``127.*``,
``::1``, ``localhost``) are out of scope.

Suppression: a top-level ``<!-- syncthing-gui-no-auth-ok -->`` XML
comment, or a ``# syncthing-gui-no-auth-ok`` shell comment, disables
all rules (use only for an isolated single-host deployment that is
firewalled off the network).

CWE refs: CWE-306 (Missing Authentication for Critical Function),
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

SUPPRESS = re.compile(
    r"<!--\s*syncthing-gui-no-auth-ok\s*-->|#\s*syncthing-gui-no-auth-ok",
    re.IGNORECASE,
)

# A <gui ...> open tag, capturing everything up to the matching
# </gui> close tag. We tolerate attributes on <gui> (tls, debugging,
# enabled, etc).
GUI_BLOCK = re.compile(
    r"(?is)<gui\b[^>]*>(?P<body>.*?)</gui\s*>",
)

ADDRESS_TAG = re.compile(r"(?is)<address\s*>\s*(?P<v>[^<]*)\s*</address\s*>")
USER_TAG = re.compile(r"(?is)<user\s*>\s*(?P<v>[^<]*)\s*</user\s*>")
PASSWORD_TAG = re.compile(r"(?is)<password\s*>\s*(?P<v>[^<]*)\s*</password\s*>")
APIKEY_TAG = re.compile(r"(?is)<apikey\s*>\s*(?P<v>[^<]*)\s*</apikey\s*>")

# Env-var style. STGUIADDRESS=0.0.0.0:8384, STGUIAPIKEY=...
ENV_GUI_ADDR = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?STGUIADDRESS
    [ \t]*[:=][ \t]*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)
ENV_GUI_APIKEY = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?STGUIAPIKEY
    [ \t]*[:=][ \t]*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)

# Public-bind heuristic. Match these as host portions, ignoring
# scheme/port noise around them.
PUBLIC_BIND_PATTERNS = (
    re.compile(r"\b0\.0\.0\.0\b"),
    re.compile(r"\[\s*::\s*\]"),
    re.compile(r"(?<![\w.])::(?!\d)"),  # bare ::
)
LOCAL_BIND_PATTERNS = (
    re.compile(r"\b127\.\d+\.\d+\.\d+\b"),
    re.compile(r"\blocalhost\b", re.IGNORECASE),
    re.compile(r"\[\s*::1\s*\]"),
    re.compile(r"(?<![\w.])::1(?![\w])"),
)


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _is_publicly_bound(addr: str) -> bool:
    if addr == "":
        return False
    if any(p.search(addr) for p in LOCAL_BIND_PATTERNS):
        return False
    return any(p.search(addr) for p in PUBLIC_BIND_PATTERNS)


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    findings: List[Tuple[int, str]] = []

    # ---- XML <gui> block(s) ----
    for gui in GUI_BLOCK.finditer(text):
        body = gui.group("body")
        body_offset = gui.start("body")
        addr_match = ADDRESS_TAG.search(body)
        if not addr_match:
            continue
        addr_value = _strip(addr_match.group("v"))
        if not _is_publicly_bound(addr_value):
            continue
        addr_line = _line_of_offset(text, body_offset + addr_match.start("v"))

        user_match = USER_TAG.search(body)
        password_match = PASSWORD_TAG.search(body)
        apikey_match = APIKEY_TAG.search(body)

        if user_match is None:
            findings.append(
                (
                    addr_line,
                    f"<gui> bound publicly to {addr_value!r} with no <user> element "
                    "(GUI / REST API reachable without basic-auth credentials)",
                )
            )
        if password_match is not None:
            pw_value = _strip(password_match.group("v"))
            if pw_value == "":
                pw_line = _line_of_offset(text, body_offset + password_match.start("v"))
                findings.append(
                    (
                        pw_line,
                        f"<gui> bound publicly to {addr_value!r} with empty <password> "
                        "(basic-auth accepts any credential)",
                    )
                )
        if apikey_match is None or _strip(apikey_match.group("v")) == "":
            line = (
                _line_of_offset(text, body_offset + apikey_match.start("v"))
                if apikey_match is not None
                else addr_line
            )
            findings.append(
                (
                    line,
                    f"<gui> bound publicly to {addr_value!r} without an <apikey> "
                    "(mutating REST endpoints have no API-key gate)",
                )
            )

    # ---- env-var style ----
    env_addr_match = ENV_GUI_ADDR.search(text)
    if env_addr_match is not None:
        addr_value = _strip(env_addr_match.group("val"))
        if _is_publicly_bound(addr_value):
            env_apikey_match = ENV_GUI_APIKEY.search(text)
            apikey_value = (
                _strip(env_apikey_match.group("val")) if env_apikey_match else ""
            )
            if apikey_value == "":
                addr_line = _line_of_offset(text, env_addr_match.start("val"))
                findings.append(
                    (
                        addr_line,
                        f"STGUIADDRESS={addr_value!r} binds publicly while STGUIAPIKEY "
                        "is unset or empty (REST API has no auth gate)",
                    )
                )

    # de-dup while preserving order
    seen: set = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    return unique


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
