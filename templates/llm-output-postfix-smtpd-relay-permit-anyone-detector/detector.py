#!/usr/bin/env python3
"""Detect Postfix main.cf configurations whose smtpd relay/recipient
restriction lists allow open-relay behavior.

Postfix evaluates ``smtpd_relay_restrictions`` (and the legacy
``smtpd_recipient_restrictions``) left-to-right. The first matching
clause wins. A bare ``permit`` token is the catch-all "allow this
mail" rule. Putting a bare ``permit`` anywhere before a
``reject_unauth_destination`` (or when no such reject is present at
all) produces an open relay (CWE-269 / CWE-732): the MTA accepts
mail destined for any RCPT-TO domain from any client.

Common LLM-generated regressions::

    smtpd_relay_restrictions = permit

    smtpd_relay_restrictions =
        permit_mynetworks
        permit
        reject_unauth_destination

    smtpd_recipient_restrictions =
        permit_mynetworks, permit, reject_unauth_destination

What's checked, per file:
  - Each top-level parameter whose key is
    ``smtpd_relay_restrictions`` or ``smtpd_recipient_restrictions``
    (Postfix uses ``key = value`` with optional indented
    continuation lines and ``\\``-newline continuations).
  - Within the folded value, presence of a bare ``permit`` token
    not followed by an underscore (so ``permit_mynetworks``,
    ``permit_sasl_authenticated``, ``permit_auth_destination``,
    ``permit_tls_clientcerts``, ``permit_inet_interfaces`` are not
    treated as the catch-all and are ignored).
  - When a bare ``permit`` is found, the file is flagged unless a
    ``reject_unauth_destination`` token appears strictly before
    that ``permit`` in the same value list.

Accepted (not flagged):
  - Standard safe shape that ends with ``reject_unauth_destination``
    (and contains no earlier bare ``permit``).
  - Files containing the comment ``# postfix-open-relay-allowed``
    (lab / honeypot fixtures).
  - Any other parameter (e.g. ``smtpd_helo_restrictions``).

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*postfix-open-relay-allowed", re.IGNORECASE)

PARAM_KEYS = {
    "smtpd_relay_restrictions",
    "smtpd_recipient_restrictions",
}

# Match the start of a parameter assignment at column 0 (Postfix
# treats leading whitespace as a continuation of the previous
# parameter's value).
PARAM_START_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<rest>.*)$"
)

# A "bare permit" token: surrounded by start, comma, or whitespace,
# and NOT followed by an underscore (so permit_mynetworks etc are
# excluded).
BARE_PERMIT_RE = re.compile(r"(?<![A-Za-z0-9_])permit(?![A-Za-z0-9_])")
REJECT_UNAUTH_RE = re.compile(
    r"(?<![A-Za-z0-9_])reject_unauth_destination(?![A-Za-z0-9_])"
)


def _strip_comment(line: str) -> str:
    # Postfix main.cf treats # as start-of-comment. There is no
    # quoting concern at the parameter-value level we examine.
    idx = line.find("#")
    if idx == -1:
        return line
    return line[:idx]


def _iter_params(source: str):
    """Yield (key, value, start_line_no) for each Postfix parameter.

    Folds indented continuations and trailing-backslash continuations.
    Line numbers are 1-based and refer to the *start* of the
    parameter (the line containing ``key =``).
    """
    # Pre-process trailing-backslash continuations: join physical
    # lines but keep a marker so line numbers stay sensible.
    raw_lines = source.splitlines()
    # First pass: handle "\\" continuations.
    joined: List[Tuple[int, str]] = []  # (orig_line_no, text)
    buf = ""
    buf_line = 0
    for idx, line in enumerate(raw_lines, start=1):
        stripped_for_bs = line.rstrip()
        if stripped_for_bs.endswith("\\"):
            if not buf:
                buf_line = idx
            buf += stripped_for_bs[:-1] + " "
            continue
        if buf:
            joined.append((buf_line, buf + line))
            buf = ""
            buf_line = 0
        else:
            joined.append((idx, line))
    if buf:
        joined.append((buf_line, buf))

    # Second pass: handle indented continuation lines.
    pending_key = None
    pending_value = ""
    pending_line = 0
    for line_no, line in joined:
        no_comment = _strip_comment(line)
        # Blank or comment-only?
        if not no_comment.strip():
            if pending_key is not None:
                yield pending_key, pending_value, pending_line
                pending_key = None
                pending_value = ""
                pending_line = 0
            continue
        # Continuation line (starts with whitespace)?
        if line and line[0] in (" ", "\t"):
            if pending_key is not None:
                pending_value += " " + no_comment.strip()
            # else: stray continuation; ignore
            continue
        # New parameter line.
        m = PARAM_START_RE.match(no_comment)
        if not m:
            # Not a parameter assignment; flush pending and skip.
            if pending_key is not None:
                yield pending_key, pending_value, pending_line
                pending_key = None
                pending_value = ""
                pending_line = 0
            continue
        # Flush previous.
        if pending_key is not None:
            yield pending_key, pending_value, pending_line
        pending_key = m.group("key")
        pending_value = m.group("rest").strip()
        pending_line = line_no
    if pending_key is not None:
        yield pending_key, pending_value, pending_line


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    for key, value, line_no in _iter_params(source):
        if key not in PARAM_KEYS:
            continue
        # Normalize commas to whitespace for token search; both are
        # valid Postfix list separators.
        normalized = value.replace(",", " ")
        permit_match = BARE_PERMIT_RE.search(normalized)
        if not permit_match:
            continue
        # Locate position of the bare permit and the (optional)
        # reject_unauth_destination. If reject precedes permit, OK.
        permit_pos = permit_match.start()
        reject_match = REJECT_UNAUTH_RE.search(normalized)
        if reject_match and reject_match.start() < permit_pos:
            continue
        findings.append(
            (
                line_no,
                f"{key} contains catch-all 'permit' without a preceding "
                f"reject_unauth_destination (open-relay risk)",
            )
        )
    return findings


def _is_postfix_main_cf(path: Path) -> bool:
    name = path.name.lower()
    if name == "main.cf":
        return True
    if name.endswith(".cf"):
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_postfix_main_cf(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
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
