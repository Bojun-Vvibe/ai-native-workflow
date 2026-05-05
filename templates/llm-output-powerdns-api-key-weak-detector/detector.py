#!/usr/bin/env python3
"""Detect PowerDNS configurations from LLM output where the
HTTP API / webserver is enabled with a weak, default, or absent
``api-key`` and bound beyond loopback.

PowerDNS Authoritative (``pdns.conf``) and PowerDNS Recursor
(``recursor.conf``) both ship an HTTP API
(https://doc.powerdns.com/authoritative/http-api/index.html) that
is the primary control plane: anyone holding the API key can add
zones, dump records, change forwarding, or in the recursor case
re-target lookups for any name. The API is gated by:

  - ``api=yes`` and ``webserver=yes``,
  - ``api-key=<secret>``, and
  - ``webserver-address`` / ``webserver-allow-from`` ACLs.

Common LLM-generated regressions:

  1. ``api=yes`` and ``webserver=yes`` with no ``api-key=`` line at
     all (older PowerDNS allowed this; modern versions still let
     the daemon start with a warning).
  2. ``api-key=`` set to an obvious placeholder (``changeme``,
     ``secret``, ``REPLACE_ME``, ``1234``, …) — equivalent to no
     auth.
  3. ``webserver-address`` set to ``0.0.0.0`` / ``::`` (or the key
     missing while ``webserver=yes``, in which case the default in
     several distro builds is also wide open) AND
     ``webserver-allow-from`` left at its permissive default
     (``0.0.0.0/0,::/0``) or absent.
  4. Both 2 AND 3 coincide — same publish-port / placeholder-key
     pattern as the Adminer template, escalated because the API
     can rewrite the recursor's view of DNS.

Suppression: a top-level ``# powerdns-api-ok`` comment in the
file disables all rules (use only when the API listener is
firewalled to a dedicated management network).

CWE refs: CWE-798 (Use of Hard-coded Credentials), CWE-306
(Missing Authentication for Critical Function), CWE-1188
(Insecure Default Initialization of Resource).

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

SUPPRESS = re.compile(r"#\s*powerdns-api-ok", re.IGNORECASE)

# In scope when any PowerDNS marker appears.
PDNS_MARKERS = [
    re.compile(r"(?im)^\s*launch\s*="),                 # pdns.conf launch=
    re.compile(r"(?im)^\s*config-dir\s*=.*pdns\b"),
    re.compile(r"(?im)^\s*image\s*:\s*[\"']?powerdns/(?:pdns-auth|pdns-recursor)"),
    re.compile(r"\bpdns\.conf\b", re.IGNORECASE),
    re.compile(r"\brecursor\.conf\b", re.IGNORECASE),
    re.compile(r"(?im)^\s*setuid\s*=\s*pdns\b"),
    re.compile(r"(?im)^\s*setgid\s*=\s*pdns\b"),
    # Combination marker: any pdns-specific key (api-key /
    # webserver-allow-from / local-address with PowerDNS-shaped
    # neighbours).
    re.compile(r"(?im)^\s*(?:api-key|webserver-allow-from|webserver-address)\s*="),
]

# Conf-style "key=value" matchers. PowerDNS .conf files are flat
# key=value, comments start with '#'.
def _kv(key: str) -> re.Pattern:
    return re.compile(
        r"(?im)^\s*" + re.escape(key) + r"\s*=\s*(?P<val>[^#\r\n]*?)\s*(?:#.*)?$"
    )


API_YES = re.compile(r"(?im)^\s*api\s*=\s*(?:yes|true|on|1)\s*(?:#.*)?$")
WEBSERVER_YES = re.compile(r"(?im)^\s*webserver\s*=\s*(?:yes|true|on|1)\s*(?:#.*)?$")
API_KEY = _kv("api-key")
WEBSERVER_ADDRESS = _kv("webserver-address")
WEBSERVER_ALLOW_FROM = _kv("webserver-allow-from")

PLACEHOLDER_VALUES = {
    "", "changeme", "change-me", "change_me", "secret", "password",
    "replace_me", "replaceme", "replace-me", "<random>", "<changeme>",
    "todo", "xxx", "xxxx", "your_secret_here", "your-secret-here",
    "yoursecrethere", "default", "example", "1234", "12345", "123456",
    "admin", "pdns", "powerdns", "test", "demo",
}

WIDE_OPEN_ALLOW = {"0.0.0.0/0", "::/0", "0.0.0.0/0,::/0", "::/0,0.0.0.0/0"}
WIDE_OPEN_BIND = {"0.0.0.0", "::", "*"}


def _is_pdns_config(text: str) -> bool:
    return any(m.search(text) for m in PDNS_MARKERS)


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _line_of_match(text: str, m: Optional[re.Match]) -> int:
    if m is None:
        return 1
    return text.count("\n", 0, m.start()) + 1


def _normalise_allow(v: str) -> str:
    # Strip whitespace inside comma-separated CIDR lists, lower-case.
    parts = [p.strip().lower() for p in v.split(",") if p.strip()]
    return ",".join(parts)


def scan(text: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(text):
        return []
    if not _is_pdns_config(text):
        return []

    findings: List[Tuple[int, str]] = []

    api_on = API_YES.search(text)
    web_on = WEBSERVER_YES.search(text)
    if not (api_on or web_on):
        return []

    api_key_m = API_KEY.search(text)
    api_key_val = _strip(api_key_m.group("val")) if api_key_m else None
    api_key_placeholder = (
        api_key_val is not None and api_key_val.lower() in PLACEHOLDER_VALUES
    )
    api_key_missing = api_key_m is None

    web_addr_m = WEBSERVER_ADDRESS.search(text)
    web_addr_val = _strip(web_addr_m.group("val")) if web_addr_m else ""
    # When webserver-address is unset, modern PowerDNS defaults to
    # 127.0.0.1, but several distro/container images override this
    # to 0.0.0.0 (e.g. powerdns/pdns-auth). We treat "missing" as
    # ambiguous and only flag explicit wide binds here.
    web_bind_public = web_addr_val in WIDE_OPEN_BIND

    web_allow_m = WEBSERVER_ALLOW_FROM.search(text)
    web_allow_val = _normalise_allow(_strip(web_allow_m.group("val"))) if web_allow_m else ""
    web_allow_open = (
        web_allow_m is None  # default in older builds is permissive
        or web_allow_val in WIDE_OPEN_ALLOW
        or web_allow_val == ""
    )

    # Rule 1: api=yes / webserver=yes with no api-key= at all.
    if (api_on or web_on) and api_key_missing:
        anchor = api_on if api_on is not None else web_on
        findings.append(
            (
                _line_of_match(text, anchor),
                "PowerDNS API/webserver enabled but no api-key= line is present; "
                "the HTTP API has no authentication",
            )
        )

    # Rule 2: api-key= set to a placeholder.
    if api_key_placeholder:
        findings.append(
            (
                _line_of_match(text, api_key_m),
                "api-key is set to a placeholder value ("
                + (api_key_val or "<empty>")
                + "); the HTTP API is effectively unauthenticated",
            )
        )

    # Rule 3: explicit public bind with permissive / absent
    # webserver-allow-from.
    if web_bind_public and web_allow_open:
        findings.append(
            (
                _line_of_match(text, web_addr_m),
                "webserver-address binds publicly (" + web_addr_val + ") with "
                "webserver-allow-from missing or set to 0.0.0.0/0,::/0; the "
                "PowerDNS HTTP API is reachable from any source",
            )
        )

    # Rule 4 escalation: placeholder/missing key AND public bind.
    if (api_key_missing or api_key_placeholder) and web_bind_public:
        # Avoid duplicating the rule-1/rule-2/rule-3 reasons; emit
        # a combined critical finding pointing at the bind line.
        findings.append(
            (
                _line_of_match(text, web_addr_m if web_addr_m else (api_key_m or api_on or web_on)),
                "CRITICAL: PowerDNS HTTP API is publicly bound AND the api-key is "
                "missing or a placeholder; an attacker can rewrite zones / "
                "forwarders remotely with no credentials",
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
