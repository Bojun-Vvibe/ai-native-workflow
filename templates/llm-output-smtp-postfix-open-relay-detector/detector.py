#!/usr/bin/env python3
"""Detect Postfix ``main.cf`` files configured as an open mail relay.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*smtp-open-relay-allowed")

# Postfix supports values that span multiple physical lines via leading
# whitespace continuation. We collapse those into logical key=value
# pairs before applying rules.
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

WIDE_CIDR_RE = re.compile(
    r"(?:(?<![\d.])0\.0\.0\.0/[0-7](?!\d)|(?<![:\w])::/0(?!\d))"
)


def _logical_lines(source: str) -> List[Tuple[int, str, str]]:
    """Return ``(line_no, raw_line, key_or_continuation)`` triples
    grouped into Postfix's logical assignments.

    Yields one tuple per assignment; ``raw_line`` is the original
    physical line where the assignment started, and the third element
    is the assembled value.
    """
    out: List[Tuple[int, str, str]] = []
    cur_line: int = 0
    cur_key: str = ""
    cur_value_parts: List[str] = []

    def flush():
        if cur_key:
            out.append((cur_line, cur_key, " ".join(cur_value_parts).strip()))

    for i, raw in enumerate(source.splitlines(), start=1):
        # Comments are full-line only in Postfix main.cf semantics.
        if raw.lstrip().startswith("#"):
            continue
        if not raw.strip():
            continue
        if raw[:1] in (" ", "\t"):
            # Continuation of previous logical assignment.
            if cur_key:
                cur_value_parts.append(raw.strip())
            continue
        # New assignment — flush previous.
        flush()
        m = ASSIGN_RE.match(raw)
        if not m:
            cur_key = ""
            cur_value_parts = []
            continue
        cur_line = i
        cur_key = m.group(1)
        cur_value_parts = [m.group(2).strip()]

    flush()
    return out


def _split_restrictions(value: str) -> List[str]:
    # Postfix restriction lists are whitespace- or comma-separated.
    parts = re.split(r"[\s,]+", value)
    return [p for p in parts if p]


def _has_sasl_gate_before_wide_permit(tokens: List[str]) -> bool:
    """Return True if a SASL/cert gate appears before any bare ``permit``.

    A bare trailing ``permit`` is what makes a list permissive; if it
    is preceded by ``permit_sasl_authenticated`` and a
    ``reject_unauth_destination`` (or ``reject``) the relay decision
    has already been narrowed.
    """
    saw_reject_unauth = False
    saw_sasl = False
    for tok in tokens:
        low = tok.lower()
        if low == "permit_sasl_authenticated":
            saw_sasl = True
        if low == "reject_unauth_destination":
            saw_reject_unauth = True
        if low == "permit":
            return saw_sasl and saw_reject_unauth
    return False


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    settings: Dict[str, Tuple[int, str]] = {}
    for line_no, key, value in _logical_lines(source):
        # Last wins, like Postfix itself.
        settings[key] = (line_no, value)

    # 1. mynetworks too wide.
    if "mynetworks" in settings:
        line_no, value = settings["mynetworks"]
        if WIDE_CIDR_RE.search(value):
            findings.append((
                line_no,
                f"mynetworks={value!r} trusts the entire internet (CIDR /0../7)",
            ))

    mynetworks_wide = (
        "mynetworks" in settings
        and bool(WIDE_CIDR_RE.search(settings["mynetworks"][1]))
    )

    # 2. smtpd_relay_restrictions resolves to permit.
    if "smtpd_relay_restrictions" in settings:
        line_no, value = settings["smtpd_relay_restrictions"]
        tokens = _split_restrictions(value)
        if tokens:
            first = tokens[0].lower()
            if first == "permit":
                findings.append((
                    line_no,
                    "smtpd_relay_restrictions starts with 'permit' — relay is open",
                ))
            elif "permit" in [t.lower() for t in tokens] and not _has_sasl_gate_before_wide_permit(tokens):
                if "reject_unauth_destination" not in [t.lower() for t in tokens]:
                    findings.append((
                        line_no,
                        "smtpd_relay_restrictions has a bare 'permit' without 'reject_unauth_destination'",
                    ))

    # 3. smtpd_recipient_restrictions missing reject_unauth_destination.
    if "smtpd_recipient_restrictions" in settings:
        line_no, value = settings["smtpd_recipient_restrictions"]
        tokens = [t.lower() for t in _split_restrictions(value)]
        if tokens and "reject_unauth_destination" not in tokens:
            # Bare 'permit' or trailing 'permit' with no auth gate is the
            # smoking gun.
            if "permit" in tokens and not _has_sasl_gate_before_wide_permit(_split_restrictions(value)):
                findings.append((
                    line_no,
                    "smtpd_recipient_restrictions allows 'permit' without 'reject_unauth_destination'",
                ))

    # 4. relay_domains wildcard / wide.
    if "relay_domains" in settings:
        line_no, value = settings["relay_domains"]
        # Bare * is wildcard; combination of $mydomain + wide mynetworks
        # is also dangerous.
        domains = _split_restrictions(value)
        if "*" in domains:
            findings.append((
                line_no,
                "relay_domains contains '*' — relays mail for any destination domain",
            ))
        elif mynetworks_wide and any(
            d.lower() in ("$mydomain", "$mydestination") for d in domains
        ):
            findings.append((
                line_no,
                "relay_domains references $mydomain while mynetworks is internet-wide",
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("main.cf", "*.main.cf", "postfix-*.cf"):
                targets.extend(sorted(path.rglob(ext)))
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
