#!/usr/bin/env python3
"""Detect RabbitMQ classic Erlang-term configs that empty the
``loopback_users`` list — the exact shape that LLM "I can't connect
to RabbitMQ from another host with guest/guest, fix it" snippets
emit.

RabbitMQ ships with a built-in user ``guest`` whose password is also
``guest``. Since 3.3.0, the broker restricts that user to loopback
connections via the ``loopback_users`` list (default
``[<<"guest">>]``). The whole reason the restriction exists is that
the default credentials are public knowledge — anyone on the network
who can reach 5672 / 5671 will try ``guest:guest`` first.

When users hit "ACCESS_REFUSED - Login was refused using
authentication mechanism PLAIN" from a remote host and ask an
assistant to fix it, the canonical wrong answer is one of:

* ``{loopback_users, []}`` (classic ``rabbitmq.config`` /
  ``advanced.config``)
* ``loopback_users.1 = none`` (newer ``rabbitmq.conf`` sysctl format)
* the equivalent in a YAML/JSON wrapper that an operator's templating
  system feeds into ``advanced.config``

Any of these turns ``guest:guest`` into a remotely usable
administrator on the default vhost. This is one of the most reliable
findings in any RabbitMQ pentest.

Rules: a finding is emitted when ANY of:

1. **Erlang term form.** A ``{loopback_users, []}`` tuple appears
   anywhere in the file (whitespace-tolerant — ``{ loopback_users ,
   [ ] }`` matches).
2. **sysctl/ini form.** A line of the form
   ``loopback_users[.<idx>] = none`` (case-insensitive, whitespace-
   tolerant). The literal sentinel ``none`` is the documented way
   to clear the list in ``rabbitmq.conf``.
3. **sysctl/ini form, explicit clear.** A line ``loopback_users =``
   with an empty value (no users listed at all).

A line containing the marker ``# rabbitmq-loopback-cleared-allowed``
suppresses the finding for the whole file (use this only when the
``guest`` user has been deleted in a separate provisioning step
that this static check cannot see).

Stdlib-only. Exit code is the count of files with at least one
finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*rabbitmq-loopback-cleared-allowed|%\s*rabbitmq-loopback-cleared-allowed")

# Erlang form: {loopback_users, []} — tolerate whitespace and newlines
ERLANG_EMPTY_RE = re.compile(
    r"\{\s*loopback_users\s*,\s*\[\s*\]\s*\}",
    re.IGNORECASE,
)

# sysctl form: loopback_users.1 = none  OR  loopback_users = none
SYSCTL_NONE_RE = re.compile(
    r"^\s*loopback_users(?:\.[0-9A-Za-z_]+)?\s*=\s*none\s*(?:[#%].*)?$",
    re.IGNORECASE,
)

# sysctl form: loopback_users =   (empty value)
SYSCTL_EMPTY_RE = re.compile(
    r"^\s*loopback_users(?:\.[0-9A-Za-z_]+)?\s*=\s*(?:[#%].*)?$",
    re.IGNORECASE,
)


def _strip_erlang_comments(source: str) -> str:
    """Erlang line comments start with %. We strip them so the term
    matcher doesn't get confused by commented-out examples."""
    out_lines = []
    for raw in source.splitlines():
        # Don't strip if % is inside a string — but our matcher only
        # cares about Erlang terms, where strings around loopback_users
        # would be unusual. Conservative: strip from first %.
        out_lines.append(raw.split("%", 1)[0])
    return "\n".join(out_lines)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    # First: Erlang-term form. Match against the comment-stripped form,
    # then map back to the line containing the start of the match.
    stripped = _strip_erlang_comments(source)
    for m in ERLANG_EMPTY_RE.finditer(stripped):
        # Locate the line number of the match start.
        line_no = stripped.count("\n", 0, m.start()) + 1
        findings.append((
            line_no,
            (
                "RabbitMQ {loopback_users, []} clears the loopback-only "
                "restriction on the default 'guest' user — guest:guest "
                "becomes a remotely usable administrator"
            ),
        ))

    # Second: sysctl / .conf form. Process line-by-line because rabbitmq.conf
    # is line-oriented and we want explicit line numbers.
    for i, raw in enumerate(source.splitlines(), start=1):
        # Skip Erlang comments and full-line # comments
        if raw.lstrip().startswith("%") or raw.lstrip().startswith("#"):
            continue
        if SYSCTL_NONE_RE.match(raw):
            findings.append((
                i,
                (
                    "RabbitMQ loopback_users = none clears the loopback-"
                    "only restriction on the default 'guest' user — "
                    "guest:guest becomes a remotely usable administrator"
                ),
            ))
            continue
        if SYSCTL_EMPTY_RE.match(raw):
            # Only flag if the line really has loopback_users on it
            # (the regex enforces that) and the value is empty.
            findings.append((
                i,
                (
                    "RabbitMQ loopback_users = <empty> clears the "
                    "loopback-only restriction on the default 'guest' "
                    "user — guest:guest becomes a remotely usable "
                    "administrator"
                ),
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in (
                "rabbitmq.config",
                "advanced.config",
                "rabbitmq.conf",
                "*.config",
                "*.conf",
            ):
                targets.extend(sorted(path.rglob(pat)))
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
