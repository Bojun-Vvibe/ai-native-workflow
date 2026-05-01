#!/usr/bin/env python3
"""Detect RabbitMQ configurations or client code that rely on the
default `guest` / `guest` credentials in a way that is reachable from
non-loopback callers.

RabbitMQ ships with a `guest` user that has admin privileges. Since
RabbitMQ 3.3 it is restricted to loopback by default via
`loopback_users = guest` (classic config) or
`loopback_users.guest = true` (new-style sysctl). LLM-generated
snippets routinely:

  * remove `guest` from `loopback_users` ("loopback_users = []"),
  * set `loopback_users.guest = false`,
  * connect to `amqp://guest:guest@<non-loopback-host>:5672/`,

which together expose a remotely-usable admin account on every
RabbitMQ node that picks up the config.

A file containing the comment marker `rabbitmq-guest-allowed` is
treated as suppressed.
"""

from __future__ import annotations

import os
import re
import sys

SUPPRESS_MARK = "rabbitmq-guest-allowed"

# `loopback_users = []`  or  `loopback_users = none`
EMPTY_LOOPBACK_CLASSIC = re.compile(
    r"""^\s*loopback_users\s*=\s*(\[\s*\]|none|\(\s*\))\s*$""",
    re.IGNORECASE | re.MULTILINE,
)

# Sysctl form: `loopback_users.guest = false`
LOOPBACK_GUEST_FALSE = re.compile(
    r"""^\s*loopback_users\.guest\s*=\s*(false|no|off|0)\s*$""",
    re.IGNORECASE | re.MULTILINE,
)

# Erlang term form often pasted into `rabbitmq.config`:
#   {loopback_users, []}
ERLANG_EMPTY_LOOPBACK = re.compile(
    r"""\{\s*loopback_users\s*,\s*\[\s*\]\s*\}""",
    re.IGNORECASE,
)

# Connection URIs that hand `guest:guest` to a non-loopback host.
GUEST_URI = re.compile(
    r"""amqps?://guest:guest@([^/\s'"]+)""",
    re.IGNORECASE,
)

# Client-code key/value pairs:
#   username = "guest"
#   password = "guest"
GUEST_CODE_USER = re.compile(
    r"""(?:username|user|userid|user_id)\s*[:=]\s*['"]guest['"]""",
    re.IGNORECASE,
)
GUEST_CODE_PASS = re.compile(
    r"""(?:password|passwd|pwd)\s*[:=]\s*['"]guest['"]""",
    re.IGNORECASE,
)

# Hosts we consider safe for guest:
LOOPBACK_HOST_RE = re.compile(
    r"""^(127\.\d+\.\d+\.\d+|::1|localhost)$""", re.IGNORECASE
)


def _is_loopback_host(host: str) -> bool:
    # Strip optional port.
    h = host.split(":", 1)[0].strip("[]")
    return bool(LOOPBACK_HOST_RE.match(h))


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []

    if EMPTY_LOOPBACK_CLASSIC.search(text):
        findings.append(
            f"{path}: loopback_users = [] / none — guest is reachable "
            f"from any network caller"
        )
    if LOOPBACK_GUEST_FALSE.search(text):
        findings.append(
            f"{path}: loopback_users.guest = false — guest is reachable "
            f"from any network caller"
        )
    if ERLANG_EMPTY_LOOPBACK.search(text):
        findings.append(
            f"{path}: Erlang config {{loopback_users, []}} — guest is "
            f"reachable from any network caller"
        )

    for m in GUEST_URI.finditer(text):
        host = m.group(1)
        if not _is_loopback_host(host):
            findings.append(
                f"{path}: amqp guest:guest URI targets non-loopback host "
                f"'{host}'"
            )

    if GUEST_CODE_USER.search(text) and GUEST_CODE_PASS.search(text):
        # Only flag if there's also a host setting that looks non-loopback.
        host_match = re.search(
            r"""(?:host|hostname|server|broker)\s*[:=]\s*['"]([^'"]+)['"]""",
            text,
            re.IGNORECASE,
        )
        if host_match and not _is_loopback_host(host_match.group(1)):
            findings.append(
                f"{path}: client code uses guest/guest against host "
                f"'{host_match.group(1)}'"
            )
        elif not host_match:
            # No explicit host -> default usually means library default,
            # which for many libs is whatever AMQP_URL or env supplies.
            # Flag conservatively.
            findings.append(
                f"{path}: client code hard-codes guest/guest credentials"
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
