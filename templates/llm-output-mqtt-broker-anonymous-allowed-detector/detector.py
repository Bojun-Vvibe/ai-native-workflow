#!/usr/bin/env python3
"""Detect MQTT broker configurations that permit anonymous clients.

Mosquitto and other MQTT brokers default-deny anonymous connections in
recent versions, but LLMs asked to "give me a working mosquitto.conf"
or "set up an MQTT broker in docker-compose" routinely emit::

    allow_anonymous true

…and skip the ``password_file`` directive, leaving the broker open to
anyone who can reach port 1883/8883. With MQTT this typically means a
remote attacker can subscribe to ``#`` (firehose every topic) and
publish arbitrary payloads to control devices.

What's flagged
--------------
A file is scanned line by line. A line is a finding when, after
stripping ``#``-comments:

* It matches ``allow_anonymous\s+true`` (mosquitto.conf style); OR
* It matches an env-var assignment ``MOSQUITTO_ALLOW_ANONYMOUS=true``
  / ``MQTT_ALLOW_ANONYMOUS=true`` (docker-compose / .env style); OR
* It matches the literal directive ``anonymous\s+yes`` (some
  alternative broker configs and HiveMQ-style snippets); OR
* It contains ``listener\s+\d+\s+0\.0\.0\.0`` *and* the same file
  also has ``allow_anonymous true`` (the canonical "public anon
  listener" pair — flagged on the listener line for clarity).

Whole-file finding (one extra entry on line 0):

* The file contains a ``listener`` directive for a non-loopback
  address AND lacks any ``password_file`` / ``psk_file`` /
  ``auth_plugin`` directive AND lacks ``allow_anonymous false``.

What's NOT flagged
------------------
* ``allow_anonymous false`` — explicit deny.
* ``listener 1883 127.0.0.1`` with no auth — loopback-only.
* Files containing ``# mqtt-anon-ok-file`` anywhere.
* Lines with a trailing ``# mqtt-anon-ok`` comment.
* ``allow_anonymous true`` inside a fenced ``# example only`` block
  bracketed by ``# mqtt-anon-ok-begin`` / ``# mqtt-anon-ok-end``.

Refs
----
* CWE-306: Missing Authentication for Critical Function
* CWE-1188: Insecure Default Initialization of Resource
* OWASP IoT Top 10 2018 I1: Weak, Guessable, or Hardcoded Passwords

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

SUPPRESS_LINE = re.compile(r"#\s*mqtt-anon-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*mqtt-anon-ok-file\b")
SUPPRESS_BEGIN = re.compile(r"#\s*mqtt-anon-ok-begin\b")
SUPPRESS_END = re.compile(r"#\s*mqtt-anon-ok-end\b")

ALLOW_ANON_TRUE = re.compile(r"^\s*allow_anonymous\s+true\b", re.IGNORECASE)
ALLOW_ANON_FALSE = re.compile(r"^\s*allow_anonymous\s+false\b", re.IGNORECASE)
ANON_YES = re.compile(r"^\s*anonymous\s+yes\b", re.IGNORECASE)
ENV_ANON = re.compile(
    r"\b(?:MOSQUITTO|MQTT|HIVEMQ)_ALLOW_ANONYMOUS\s*[:=]\s*[\"']?true[\"']?\b",
    re.IGNORECASE,
)
LISTENER = re.compile(r"^\s*listener\s+(\d+)(?:\s+(\S+))?", re.IGNORECASE)
AUTH_DIRECTIVE = re.compile(
    r"^\s*(password_file|psk_file|auth_plugin|use_identity_as_username|use_subject_as_username|require_certificate\s+true)\b",
    re.IGNORECASE,
)

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _is_loopback(addr: str) -> bool:
    return addr.strip().lower() in LOOPBACK


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    lines = source.splitlines()

    # First pass: build suppressed-line set from begin/end fences.
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

    has_allow_anon_true = False
    has_allow_anon_false = False
    has_auth = False
    has_nonloopback_listener = False

    for i, raw in enumerate(lines, start=1):
        if i in suppressed or SUPPRESS_LINE.search(raw):
            continue
        body = _strip_comment(raw)
        if ALLOW_ANON_TRUE.search(body):
            has_allow_anon_true = True
            findings.append((i, "allow_anonymous true permits unauthenticated MQTT clients"))
            continue
        if ALLOW_ANON_FALSE.search(body):
            has_allow_anon_false = True
        if ANON_YES.search(body):
            findings.append((i, "anonymous yes permits unauthenticated MQTT clients"))
            continue
        if ENV_ANON.search(raw):
            findings.append((i, "MQTT broker env var sets allow-anonymous to true"))
            continue
        if AUTH_DIRECTIVE.search(body):
            has_auth = True
        m = LISTENER.match(body)
        if m:
            addr = m.group(2) or "0.0.0.0"
            if not _is_loopback(addr):
                has_nonloopback_listener = True

    # Whole-file finding: public listener with no auth and no explicit deny.
    if (
        has_nonloopback_listener
        and not has_auth
        and not has_allow_anon_false
        and not has_allow_anon_true  # already flagged above; avoid double
    ):
        findings.append((
            0,
            "non-loopback listener without password_file / psk_file / auth_plugin and no allow_anonymous false",
        ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "mosquitto.conf",
        "*.mosquitto.conf",
        "mqtt.conf",
        "*.mqtt.conf",
        "docker-compose*.y*ml",
        ".env",
        "*.env",
        "hivemq.conf",
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
