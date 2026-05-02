#!/usr/bin/env python3
"""Detect Jenkins ``config.xml`` files that grant anonymous (unsigned-in)
users read or higher access to the controller.

Background
----------
Jenkins authorization is controlled by an ``<authorizationStrategy>``
element in ``$JENKINS_HOME/config.xml``. Several common shapes leave
the controller readable — and sometimes writable — by anyone who can
reach the HTTP port:

* ``hudson.security.AuthorizationStrategy$Unsecured`` — the
  legacy "anyone can do anything" strategy.
* ``hudson.security.LegacyAuthorizationStrategy`` — non-admins (which
  includes anonymous) get read.
* ``hudson.security.FullControlOnceLoggedInAuthorizationStrategy`` with
  ``<denyAnonymousReadAccess>false</denyAnonymousReadAccess>`` (or that
  child element absent — Jenkins defaults to *false*, i.e. anonymous
  read is allowed).
* ``hudson.security.GlobalMatrixAuthorizationStrategy`` /
  ``hudson.security.ProjectMatrixAuthorizationStrategy`` with a
  ``<permission>`` granting anything to ``anonymous`` other than the
  no-op ``hudson.model.Hudson.Read`` denial-style entry. Specifically
  flagged: any ``<permission>...:anonymous</permission>`` whose left
  side is a real Jenkins permission ID.

LLMs asked to "set up Jenkins so my CI can be browsed" routinely paste
``<denyAnonymousReadAccess>false</denyAnonymousReadAccess>`` or even
``<authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>``
without flagging that the controller is now world-writable.

What's flagged
--------------
Per file, the scanner reports a finding when any of the following
appear in the XML:

1. ``<authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>``
2. ``<authorizationStrategy class="hudson.security.LegacyAuthorizationStrategy"/>``
3. A ``FullControlOnceLoggedInAuthorizationStrategy`` block whose
   ``<denyAnonymousReadAccess>`` is ``false`` *or* missing entirely.
4. A matrix-style ``<permission>...:anonymous</permission>`` line where
   the permission is anything other than commented-out.

What's NOT flagged
------------------
* ``FullControlOnceLoggedInAuthorizationStrategy`` with
  ``<denyAnonymousReadAccess>true</denyAnonymousReadAccess>``.
* Matrix strategies that grant permissions only to ``authenticated``
  or to named users.
* Lines suppressed with a trailing ``<!-- jenkins-anon-ok -->`` XML
  comment on the same line.
* Files containing ``<!-- jenkins-anon-ok-file -->`` anywhere.

CWE refs
--------
* CWE-284: Improper Access Control
* CWE-306: Missing Authentication for Critical Function
* CWE-287: Improper Authentication

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

SUPPRESS_LINE = re.compile(r"<!--\s*jenkins-anon-ok\s*-->")
SUPPRESS_FILE = re.compile(r"<!--\s*jenkins-anon-ok-file\s*-->")

UNSECURED_RE = re.compile(
    r'<authorizationStrategy\b[^>]*class="hudson\.security\.AuthorizationStrategy\$Unsecured"',
)
LEGACY_RE = re.compile(
    r'<authorizationStrategy\b[^>]*class="hudson\.security\.LegacyAuthorizationStrategy"',
)
FULL_OPEN_RE = re.compile(
    r'<authorizationStrategy\b[^>]*class="hudson\.security\.FullControlOnceLoggedInAuthorizationStrategy"',
)
DENY_ANON_RE = re.compile(
    r"<denyAnonymousReadAccess>\s*(true|false)\s*</denyAnonymousReadAccess>",
    re.IGNORECASE,
)
# Matrix permission line:
#   <permission>hudson.model.Hudson.Read:anonymous</permission>
PERMISSION_ANON_RE = re.compile(
    r"<permission>\s*([A-Za-z0-9_.$]+)\s*:\s*anonymous\s*</permission>",
)


def _strip_xml_comments(source: str) -> str:
    """Remove block XML comments so they can't accidentally satisfy a
    pattern. We keep line numbers intact by replacing comment bodies
    with newlines as needed."""
    out: List[str] = []
    i = 0
    while i < len(source):
        j = source.find("<!--", i)
        if j == -1:
            out.append(source[i:])
            break
        out.append(source[i:j])
        end = source.find("-->", j + 4)
        if end == -1:
            # Unterminated comment — bail out, keep the rest as-is.
            out.append(source[j:])
            break
        # Replace the comment body with newlines so line numbers stay aligned.
        chunk = source[j:end + 3]
        out.append("\n" * chunk.count("\n"))
        i = end + 3
    return "".join(out)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    cleaned = _strip_xml_comments(source)
    raw_lines = source.splitlines()
    cleaned_lines = cleaned.splitlines()

    # 1) Per-line literal patterns.
    for i, raw in enumerate(raw_lines, start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        cline = cleaned_lines[i - 1] if i - 1 < len(cleaned_lines) else ""
        if UNSECURED_RE.search(cline):
            findings.append((
                i,
                "AuthorizationStrategy$Unsecured: anyone can do anything",
            ))
        if LEGACY_RE.search(cline):
            findings.append((
                i,
                "LegacyAuthorizationStrategy: anonymous gets read",
            ))
        m = PERMISSION_ANON_RE.search(cline)
        if m:
            perm = m.group(1)
            findings.append((
                i,
                f"matrix permission granted to anonymous: {perm}",
            ))

    # 2) Block-level: FullControlOnceLoggedIn without
    #    denyAnonymousReadAccess=true.
    for fmatch in FULL_OPEN_RE.finditer(cleaned):
        # Find the enclosing line number.
        start = fmatch.start()
        line_no = cleaned[:start].count("\n") + 1
        if SUPPRESS_LINE.search(raw_lines[line_no - 1] if line_no - 1 < len(raw_lines) else ""):
            continue
        # Look in a reasonable window (next 40 lines, or up to the
        # closing </authorizationStrategy>) for denyAnonymousReadAccess.
        end_tag = cleaned.find("</authorizationStrategy>", start)
        block = cleaned[start:end_tag] if end_tag != -1 else cleaned[start:start + 4000]
        deny = DENY_ANON_RE.search(block)
        if deny is None:
            findings.append((
                line_no,
                "FullControlOnceLoggedInAuthorizationStrategy without "
                "<denyAnonymousReadAccess>true</denyAnonymousReadAccess> "
                "(default allows anonymous read)",
            ))
        elif deny.group(1).lower() == "false":
            findings.append((
                line_no,
                "FullControlOnceLoggedInAuthorizationStrategy with "
                "<denyAnonymousReadAccess>false</denyAnonymousReadAccess>",
            ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    for pattern in ("config.xml", "*.config.xml", "jenkins-*.xml"):
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
