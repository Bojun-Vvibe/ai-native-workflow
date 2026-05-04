#!/usr/bin/env python3
"""Detect Prometheus deployments from LLM output that expose the
HTTP server (``--web.listen-address``) on a non-loopback bind
without enabling the ``web.config.file`` TLS / basic-auth gate.

Since Prometheus 2.24 the binary ships native TLS and basic-auth
support via the ``--web.config.file=/path/web.yml`` flag, and the
upstream docs state this is the supported mechanism for protecting
the HTTP API. LLMs commonly produce one of three unsafe shapes:

  1. A ``command:`` / ``args:`` array (compose, k8s, systemd
     ``ExecStart=``) that includes ``--web.listen-address=:9090``
     (or ``0.0.0.0:9090``) but **no** ``--web.config.file=`` flag.
  2. A ``--web.enable-admin-api`` flag enabled together with a
     non-loopback listen-address and no ``--web.config.file``
     (the admin API can wipe TSDB and snapshot data).
  3. A ``--web.enable-lifecycle`` flag enabled together with a
     non-loopback listen-address and no ``--web.config.file``
     (the lifecycle API can reload config / shut the server down).
  4. A ``web.yml`` referenced by ``--web.config.file=`` that
     contains an empty ``tls_server_config: {}`` and an empty
     ``basic_auth_users: {}`` (file present, but neither gate
     actually configured).

The detector also recognises the equivalent shapes inside YAML /
JSON / shell snippets (single-quoted, double-quoted, equals or
space separator).

Suppression: a top-level ``# prometheus-public-readonly-ok``
comment in the file disables all rules (intentional public mirror).

Public API:
    detect(text: str) -> bool
    scan(text: str)   -> list[(line, reason)]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*prometheus-public-readonly-ok", re.IGNORECASE)

# --web.listen-address=HOST:PORT or  --web.listen-address HOST:PORT
_LISTEN = re.compile(
    r"""--web\.listen-address[=\s]+["']?
        (?P<host>[0-9a-zA-Z\.\-\[\]:]*?)
        (?::(?P<port>\d+))?["']?(?=[\s"'\]]|$)""",
    re.VERBOSE,
)
_WEB_CONFIG = re.compile(r"--web\.config\.file[=\s]+[^\s#\\]+")
_ADMIN_API = re.compile(r"--web\.enable-admin-api(?![A-Za-z0-9_-])")
_LIFECYCLE = re.compile(r"--web\.enable-lifecycle(?![A-Za-z0-9_-])")

# Empty web-config YAML markers.
# Inline empty: literal `{}` / `null` / `~` value.
_TLS_EMPTY_INLINE = re.compile(
    r"(?im)^[\t ]*tls_server_config[\t ]*:[\t ]*(\{\}|null|~)[\t ]*(?:#.*)?$",
)
# Block header: bare `tls_server_config:` (we then inspect indented children).
_TLS_BLOCK = re.compile(r"(?im)^[\t ]*tls_server_config[\t ]*:[\t ]*(?:#.*)?$")
_BASIC_EMPTY_INLINE = re.compile(
    r"(?im)^[\t ]*basic_auth_users[\t ]*:[\t ]*(\{\}|null|~)[\t ]*(?:#.*)?$",
)
_BASIC_BLOCK = re.compile(r"(?im)^[\t ]*basic_auth_users[\t ]*:[\t ]*(?:#.*)?$")
# any indented child line counts as "non-empty"
_INDENTED_CHILD = re.compile(r"^[\t ]+\S")


def _is_loopback(host: str) -> bool:
    if host is None:
        return False
    h = host.strip().strip("[]").lower()
    if h == "":
        # `:9090` (no host) means all interfaces in the Prometheus
        # binary — treat as public.
        return False
    if h == "localhost":
        return True
    if h.startswith("127."):
        return True
    if h == "::1":
        return True
    return False


def _strip_comments(text: str) -> str:
    """Remove ``# ...`` line comments while preserving line numbering.

    Quotes inside comments are not handled (best-effort); good enough
    for shell / compose / systemd / yaml snippets that LLMs emit.
    """
    out_lines = []
    for line in text.splitlines():
        # respect ``#`` only when it begins a comment (after whitespace
        # or at the start). Don't strip ``#`` inside quoted values.
        in_squote = False
        in_dquote = False
        cut = None
        for i, ch in enumerate(line):
            if ch == "'" and not in_dquote:
                in_squote = not in_squote
            elif ch == '"' and not in_squote:
                in_dquote = not in_dquote
            elif ch == "#" and not in_squote and not in_dquote:
                if i == 0 or line[i - 1] in (" ", "\t"):
                    cut = i
                    break
        out_lines.append(line[:cut] if cut is not None else line)
    return "\n".join(out_lines)


def _line_of(text: str, m: re.Match) -> int:
    return text.count("\n", 0, m.start()) + 1


def _block_is_empty(text: str, block_match: re.Match) -> bool:
    """Return True if the block header is followed by no indented children."""
    tail = text[block_match.end():]
    # find next non-blank line
    for line in tail.splitlines():
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        return not _INDENTED_CHILD.match(line)
    return True


def scan(text: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(text):
        return []
    # strip line comments so `# --web.config.file ...` notes in
    # docstrings / yaml comments don't false-trigger matches.
    text = _strip_comments(text)
    findings: List[Tuple[int, str]] = []

    listens = list(_LISTEN.finditer(text))
    has_web_config = _WEB_CONFIG.search(text) is not None
    admin = _ADMIN_API.search(text)
    lifecycle = _LIFECYCLE.search(text)

    public_listen: List[re.Match] = []
    for m in listens:
        host = m.group("host") or ""
        if not _is_loopback(host):
            public_listen.append(m)

    # Rule 1: any non-loopback listen with no --web.config.file
    if public_listen and not has_web_config:
        m = public_listen[0]
        findings.append(
            (
                _line_of(text, m),
                "--web.listen-address binds a non-loopback interface but no "
                "--web.config.file is set (no TLS / basic-auth gate on the "
                "HTTP API)",
            )
        )

    # Rule 2: admin API + public listen + no web.config.file
    if admin and public_listen and not has_web_config:
        findings.append(
            (
                _line_of(text, admin),
                "--web.enable-admin-api on a public listen-address with no "
                "--web.config.file (admin API can wipe TSDB / snapshot data)",
            )
        )

    # Rule 3: lifecycle API + public listen + no web.config.file
    if lifecycle and public_listen and not has_web_config:
        findings.append(
            (
                _line_of(text, lifecycle),
                "--web.enable-lifecycle on a public listen-address with no "
                "--web.config.file (lifecycle API can reload / shut down)",
            )
        )

    # Rule 4: web.yml-style config present in same blob, but TLS and
    # basic_auth blocks are both empty → no actual gate.
    tls_empty_inline = _TLS_EMPTY_INLINE.search(text)
    tls_block = _TLS_BLOCK.search(text)
    basic_empty_inline = _BASIC_EMPTY_INLINE.search(text)
    basic_block = _BASIC_BLOCK.search(text)

    tls_present_but_empty = False
    tls_anchor = None
    basic_present_but_empty = False
    basic_anchor = None
    if tls_empty_inline is not None:
        tls_present_but_empty = True
        tls_anchor = tls_empty_inline
    elif tls_block is not None:
        if _block_is_empty(text, tls_block):
            tls_present_but_empty = True
            tls_anchor = tls_block
    if basic_empty_inline is not None:
        basic_present_but_empty = True
        basic_anchor = basic_empty_inline
    elif basic_block is not None:
        if _block_is_empty(text, basic_block):
            basic_present_but_empty = True
            basic_anchor = basic_block

    if tls_present_but_empty and basic_present_but_empty:
        findings.append(
            (
                _line_of(text, tls_anchor),
                "web-config file declares tls_server_config and "
                "basic_auth_users but both are empty (no gate actually "
                "configured)",
            )
        )

    seen: set = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    return unique


def detect(text: str) -> bool:
    return bool(scan(text))


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
