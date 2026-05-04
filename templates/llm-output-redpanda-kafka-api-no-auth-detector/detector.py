#!/usr/bin/env python3
"""Detect Redpanda configuration snippets emitted by LLMs that expose
the Kafka API on a non-loopback bind without enabling SASL or mTLS.

Redpanda is a Kafka-API-compatible streaming broker. By default the
Kafka API listens on ``0.0.0.0:9092`` with **no authentication and no
TLS**. The supported way to gate it is to declare a listener with a
matching ``kafka_api_tls`` entry that requires the client cert
(``require_client_auth: true``) and/or to enable SASL via
``enable_sasl: true`` plus a matching ``authentication_method: sasl``
on the listener.

LLMs commonly emit one of these unsafe shapes when asked
"give me a redpanda.yaml" or "deploy redpanda on kubernetes":

  1. A ``kafka_api:`` block that binds to ``0.0.0.0`` (or any non
     loopback) with no matching ``kafka_api_tls:`` entry **and** no
     ``enable_sasl: true`` / ``authentication_method: sasl``.
  2. A ``kafka_api_tls:`` entry where ``enabled: true`` but
     ``require_client_auth: false`` (TLS is on but anyone with the
     server cert can still connect anonymously) **and** no SASL.
  3. CLI flag ``--set redpanda.kafka_api[0].address=0.0.0.0`` (helm /
     rpk style) without a corresponding ``--set
     redpanda.enable_sasl=true`` or kafka_api_tls override.
  4. ``superusers: ["admin"]`` declared but ``enable_sasl: false`` /
     absent - superusers list is a no-op without SASL turned on, and
     LLMs frequently include it as if it secured the cluster.

Suppression: a top-level ``# redpanda-public-readonly-ok`` comment in
the file disables all rules (intentional public broker).

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

SUPPRESS = "redpanda-public-readonly-ok"


def _strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            nl = "\n" if line.endswith("\n") else ""
            out.append(nl)
            continue
        idx = -1
        in_quote = None
        for i, ch in enumerate(line):
            if in_quote:
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in "\"'":
                in_quote = ch
                continue
            if ch == "#" and (i == 0 or line[i - 1].isspace()):
                idx = i
                break
        if idx >= 0:
            tail = "\n" if line.endswith("\n") else ""
            out.append(line[:idx].rstrip() + tail)
        else:
            out.append(line)
    return "".join(out)


def _is_loopback(addr: str) -> bool:
    a = addr.strip().strip("\"'").lower()
    if a in {"127.0.0.1", "::1", "localhost", ""}:
        return True
    if a.startswith("127."):
        return True
    return False


# --- helpers to find values across yaml/cli/json forms ---

_BOOL_TRUE = re.compile(r"""(?ix) ^ \s* (true|yes|on|1) \s* $ """)
_BOOL_FALSE = re.compile(r"""(?ix) ^ \s* (false|no|off|0) \s* $ """)


def _value_truthy(s: str) -> bool:
    return bool(_BOOL_TRUE.match(s))


def _value_falsy(s: str) -> bool:
    return bool(_BOOL_FALSE.match(s))


# kafka_api address occurrences (yaml ``- address: x`` or CLI
# ``redpanda.kafka_api[0].address=x``).
_KAFKA_ADDR_YAML_RE = re.compile(
    r"""(?im)
    ^\s*
    (?:-\s*)?
    address
    \s*:\s*
    ["']?
    (?P<addr>[0-9a-fA-F:.]+)
    ["']?
    """,
    re.VERBOSE,
)

_KAFKA_ADDR_CLI_RE = re.compile(
    r"""(?ix)
    redpanda\.kafka_api(?:\[\d+\])?\.address
    \s*=\s*
    ["']?
    (?P<addr>[0-9a-fA-F:.]+)
    ["']?
    """,
)

# Whether the file declares a kafka_api: block at all (so we only flag
# files that actually configure the kafka api).
_KAFKA_API_BLOCK_RE = re.compile(r"""(?im) ^\s* kafka_api \s* :""", re.VERBOSE)

# Whether enable_sasl is truthy anywhere in the file.
_ENABLE_SASL_RE = re.compile(
    r"""(?im) ^\s* enable_sasl \s* :\s* (?P<v>\S+) """, re.VERBOSE
)
_ENABLE_SASL_CLI_RE = re.compile(
    r"""(?ix) redpanda\.enable_sasl \s* =\s* (?P<v>\S+) """,
)

# authentication_method on a listener (sasl|none|mtls_identity).
_AUTH_METHOD_RE = re.compile(
    r"""(?im) ^\s* authentication_method \s* :\s* ["']? (?P<v>[A-Za-z_]+) ["']? """,
    re.VERBOSE,
)

# kafka_api_tls block presence.
_KAFKA_TLS_BLOCK_RE = re.compile(r"""(?im) ^\s* kafka_api_tls \s* :""", re.VERBOSE)

# Pull out enabled / require_client_auth values within the file (we treat
# them globally - good enough for LLM-output sized snippets).
_TLS_ENABLED_RE = re.compile(
    r"""(?im) ^\s* enabled \s* :\s* (?P<v>\S+) """, re.VERBOSE
)
_REQUIRE_CLIENT_AUTH_RE = re.compile(
    r"""(?im) ^\s* require_client_auth \s* :\s* (?P<v>\S+) """, re.VERBOSE
)

_SUPERUSERS_RE = re.compile(r"""(?im) ^\s* superusers \s* :""", re.VERBOSE)


def scan(text: str) -> list[tuple[int, str]]:
    if SUPPRESS in text:
        return []
    cleaned = _strip_comments(text)
    findings: list[tuple[int, str]] = []

    def line_of(pos: int) -> int:
        return cleaned.count("\n", 0, pos) + 1

    # Determine global SASL / TLS posture.
    sasl_on = False
    for m in _ENABLE_SASL_RE.finditer(cleaned):
        if _value_truthy(m.group("v")):
            sasl_on = True
            break
    if not sasl_on:
        for m in _ENABLE_SASL_CLI_RE.finditer(cleaned):
            if _value_truthy(m.group("v")):
                sasl_on = True
                break
    # listener-level sasl
    listener_sasl = any(
        m.group("v").lower() in {"sasl", "mtls_identity", "mtls"}
        for m in _AUTH_METHOD_RE.finditer(cleaned)
    )
    sasl_effectively_on = sasl_on or listener_sasl

    # TLS posture.
    tls_block = bool(_KAFKA_TLS_BLOCK_RE.search(cleaned))
    tls_enabled_vals = [m.group("v") for m in _TLS_ENABLED_RE.finditer(cleaned)]
    tls_enabled = any(_value_truthy(v) for v in tls_enabled_vals)
    require_client_auth_vals = [
        m.group("v") for m in _REQUIRE_CLIENT_AUTH_RE.finditer(cleaned)
    ]
    require_client_auth = any(_value_truthy(v) for v in require_client_auth_vals)
    require_client_auth_explicit_false = any(
        _value_falsy(v) for v in require_client_auth_vals
    )

    mtls_effectively_on = tls_block and tls_enabled and require_client_auth

    has_kafka_api_block = bool(_KAFKA_API_BLOCK_RE.search(cleaned))
    addr_matches: list[tuple[int, str]] = []
    if has_kafka_api_block:
        for m in _KAFKA_ADDR_YAML_RE.finditer(cleaned):
            addr_matches.append((m.start(), m.group("addr")))
    for m in _KAFKA_ADDR_CLI_RE.finditer(cleaned):
        addr_matches.append((m.start(), m.group("addr")))

    # Rule 1 + Rule 3: non-loopback bind without SASL and without mTLS.
    for pos, addr in addr_matches:
        if _is_loopback(addr):
            continue
        if not sasl_effectively_on and not mtls_effectively_on:
            findings.append(
                (
                    line_of(pos),
                    f"kafka_api bound to {addr!r} without enable_sasl/authentication_method=sasl and without kafka_api_tls require_client_auth",
                )
            )

    # Rule 2: TLS on but require_client_auth explicitly false, no SASL.
    if (
        tls_block
        and tls_enabled
        and require_client_auth_explicit_false
        and not sasl_effectively_on
    ):
        # Anchor finding at the first explicit false occurrence.
        for m in _REQUIRE_CLIENT_AUTH_RE.finditer(cleaned):
            if _value_falsy(m.group("v")):
                findings.append(
                    (
                        line_of(m.start()),
                        "kafka_api_tls enabled but require_client_auth=false and SASL not enabled - clients connect anonymously over TLS",
                    )
                )
                break

    # Rule 4: superusers declared but enable_sasl off/absent (and no
    # listener-level sasl). This is independent of bind address.
    if _SUPERUSERS_RE.search(cleaned) and not sasl_effectively_on:
        m = _SUPERUSERS_RE.search(cleaned)
        assert m is not None
        findings.append(
            (
                line_of(m.start()),
                "superusers declared but enable_sasl is not true - superuser list is a no-op without SASL",
            )
        )

    findings.sort(key=lambda t: t[0])
    return findings


def detect(text: str) -> bool:
    return bool(scan(text))


def _cli(argv: list[str]) -> int:
    if not argv:
        text = sys.stdin.read()
        hits = scan(text)
        for ln, reason in hits:
            print(f"<stdin>:{ln}: {reason}")
        return 1 if hits else 0

    files_with_hits = 0
    for arg in argv:
        p = Path(arg)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"{arg}: cannot read: {e}", file=sys.stderr)
            files_with_hits += 1
            continue
        hits = scan(text)
        if hits:
            files_with_hits += 1
            for ln, reason in hits:
                print(f"{arg}:{ln}: {reason}")
    return files_with_hits


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
