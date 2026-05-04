#!/usr/bin/env python3
"""Detect JupyterHub ``jupyterhub_config.py`` files that wire the
``DummyAuthenticator`` (every login succeeds with any password) on a
hub that is reachable from a non-loopback interface.

The DummyAuthenticator ships in ``dummyauthenticator`` and is also
re-exported by JupyterHub itself for testing. Setting
``c.JupyterHub.authenticator_class = 'dummy'`` (or
``'dummyauthenticator.DummyAuthenticator'``) means *any* username with
*any* password is accepted, and that user gets a single-user notebook
server with arbitrary code execution.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"^\s*#\s*jupyterhub-dummy-auth-allowed\s*$", re.MULTILINE)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1", ""}

# c.JupyterHub.authenticator_class = 'dummy'
#                                   = "dummyauthenticator.DummyAuthenticator"
#                                   = DummyAuthenticator   (imported class)
AUTH_ASSIGN = re.compile(
    r"""^\s*c\.JupyterHub\.authenticator_class\s*=\s*(?P<rhs>.+?)\s*(?:\#.*)?$""",
    re.MULTILINE,
)

DUMMY_VALUES = {
    "dummy",
    "dummyauthenticator",
    "dummyauthenticator.dummyauthenticator",
    "jupyterhub.auth.dummyauthenticator",
    "dummyauthenticator",
}

DUMMY_CLASS_TOKEN = re.compile(r"\bDummyAuthenticator\b")

# c.JupyterHub.ip = '0.0.0.0'  /  c.JupyterHub.bind_url = 'http://0.0.0.0:8000'
IP_ASSIGN = re.compile(
    r"""^\s*c\.JupyterHub\.ip\s*=\s*['"]([^'"]*)['"]""",
    re.MULTILINE,
)
BIND_URL_ASSIGN = re.compile(
    r"""^\s*c\.JupyterHub\.bind_url\s*=\s*['"](?P<url>[^'"]+)['"]""",
    re.MULTILINE,
)
HUB_IP_ASSIGN = re.compile(
    r"""^\s*c\.JupyterHub\.hub_ip\s*=\s*['"]([^'"]*)['"]""",
    re.MULTILINE,
)


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _normalize_rhs(rhs: str) -> str:
    val = rhs.strip().strip(",")
    # Strip surrounding quotes if it's a string literal.
    if (val.startswith("'") and val.endswith("'")) or (
        val.startswith('"') and val.endswith('"')
    ):
        return val[1:-1].strip().lower()
    return val.strip()


def _host_from_bind_url(url: str) -> str:
    # http://host:port/prefix  ->  host
    m = re.match(r"^[a-zA-Z]+://(?P<host>\[[^\]]+\]|[^:/]+)", url)
    if not m:
        return ""
    host = m.group("host")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host


def _exposed(source: str) -> Tuple[bool, str]:
    bind_desc = "<default 0.0.0.0>"  # JupyterHub default is all interfaces
    seen_explicit = False
    for m in IP_ASSIGN.finditer(source):
        ip = m.group(1).strip()
        seen_explicit = True
        if ip not in LOOPBACK_HOSTS and not ip.startswith("127."):
            return True, ip
        bind_desc = ip or "<empty>"
    for m in BIND_URL_ASSIGN.finditer(source):
        host = _host_from_bind_url(m.group("url"))
        seen_explicit = True
        if host and host not in LOOPBACK_HOSTS and not host.startswith("127."):
            return True, host
        bind_desc = host or "<empty>"
    if not seen_explicit:
        # Default JupyterHub.ip is '' which binds to all interfaces.
        return True, bind_desc
    return False, bind_desc


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    dummy_hits: List[Tuple[int, str]] = []
    for m in AUTH_ASSIGN.finditer(source):
        rhs = m.group("rhs")
        norm = _normalize_rhs(rhs)
        line = _line_of(source, m.start())
        if norm in DUMMY_VALUES or norm.endswith(".dummyauthenticator"):
            dummy_hits.append((line, f"authenticator_class={rhs.strip()}"))
            continue
        # Bare class assignment like = DummyAuthenticator
        if DUMMY_CLASS_TOKEN.search(rhs):
            dummy_hits.append((line, f"authenticator_class={rhs.strip()}"))

    if not dummy_hits:
        return findings

    exposed, bind_desc = _exposed(source)
    if not exposed:
        return findings

    for line, what in dummy_hits:
        findings.append(
            (
                line,
                f"JupyterHub DummyAuthenticator wired ({what}); accepts any "
                f"username/password on bind={bind_desc}",
            )
        )
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("jupyterhub_config.py")))
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
