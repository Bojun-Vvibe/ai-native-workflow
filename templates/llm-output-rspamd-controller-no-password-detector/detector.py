#!/usr/bin/env python3
"""Detect rspamd controller worker configurations that ship with no
password / enable_password set, leaving the WebUI + management API
exposed without authentication.

Surfaces scanned:

* ``worker-controller.inc`` / ``controller.conf`` — UCL config with a
  ``worker "controller" { ... }`` (or ``type = "controller"``) block
  that lacks both ``password`` and ``enable_password``.
* ``local.d/worker-controller.inc`` overrides where the operator
  explicitly sets ``password = "";`` (empty literal).
* ``docker-compose.yml`` / ``Dockerfile`` invocations of
  ``rspamd ... -p ""`` or env var ``RSPAMD_PASSWORD=""`` /
  ``RSPAMD_PASSWORD=q1`` (the upstream "default" example password).

Suppression: a magic comment ``# rspamd-controller-no-password-allowed``
on the same line or the line directly above silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*rspamd-controller-no-password-allowed")

# Default upstream example password from rspamd docs that operators
# commonly leave in place when copying the snippet verbatim.
KNOWN_WEAK_LITERALS = {"q1", "password", "rspamd", "admin", "changeme", ""}

CONTROLLER_BLOCK_OPEN = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        worker\s*"?controller"?\s*\{      # worker "controller" {
      | type\s*=\s*"?controller"?         # type = "controller"
    )
    """
)
PASSWORD_LINE = re.compile(
    r"""(?ix)
    ^\s*
    (enable_password|password)
    \s*=\s*
    (?:
        "([^"]*)"
      | '([^']*)'
      | (\S+)
    )
    \s*;?\s*(?:\#.*)?$
    """
)
CLOSE_BRACE = re.compile(r"^\s*\}\s*$")


def _scan_ucl(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        if CONTROLLER_BLOCK_OPEN.search(lines[i]):
            block_start = i
            depth = lines[i].count("{") - lines[i].count("}")
            j = i + 1
            block_lines: List[Tuple[int, str]] = []
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                block_lines.append((j, lines[j]))
                j += 1
            # Standalone "type = controller" with no braces: scan the
            # whole file as a single controller scope.
            if "{" not in lines[block_start]:
                block_lines = [(k, lines[k]) for k in range(len(lines))]
            has_password = False
            weak_password_line = -1
            weak_reason = ""
            for ln, raw in block_lines:
                m = PASSWORD_LINE.match(raw)
                if not m:
                    continue
                value = m.group(2) if m.group(2) is not None else (
                    m.group(3) if m.group(3) is not None else (m.group(4) or "")
                )
                if value.strip().lower() in KNOWN_WEAK_LITERALS:
                    weak_password_line = ln + 1
                    weak_reason = (
                        f"rspamd controller {m.group(1)} = "
                        f"{value!r} is a known weak/default literal"
                    )
                else:
                    has_password = True
            if weak_password_line > 0:
                findings.append((weak_password_line, weak_reason))
            elif not has_password:
                findings.append(
                    (
                        block_start + 1,
                        "rspamd controller block defines no password / "
                        "enable_password (WebUI + API unauthenticated)",
                    )
                )
            i = j if j > i else i + 1
        else:
            i += 1
    return findings


COMPOSE_ENV_BLANK = re.compile(
    r"""(?ix)
    ^\s*-?\s*
    RSPAMD_PASSWORD
    \s*[:=]\s*
    (?:
        ""
      | ''
      | (q1|password|rspamd|admin|changeme)
      | $
    )
    """
)
DOCKER_CLI_FLAG = re.compile(
    r"""(?ix)
    rspamd(?:adm|c|d|)\b
    [^\n]*?
    (?:
        \s-p\s+(?:""|'')              # shell form: rspamd ... -p ""
      | "-p"\s*,\s*""                  # JSON exec form: "-p", ""
      | '-p'\s*,\s*''                  # JSON exec form, single-quoted
    )
    """
)


def _scan_compose_or_dockerfile(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        if COMPOSE_ENV_BLANK.search(raw):
            findings.append(
                (i, "RSPAMD_PASSWORD env is blank or a known weak literal")
            )
        elif DOCKER_CLI_FLAG.search(raw):
            findings.append(
                (i, 'rspamd CLI invoked with -p "" (empty controller password)')
            )
    return findings


def _filter_suppressed(
    lines: List[str], findings: List[Tuple[int, str]]
) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for ln, msg in findings:
        same = lines[ln - 1] if 0 < ln <= len(lines) else ""
        prev = lines[ln - 2] if ln - 2 >= 0 else ""
        if SUPPRESS.search(same) or SUPPRESS.search(prev):
            continue
        out.append((ln, msg))
    return out


def scan_file(path: Path) -> List[Tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    name = path.name.lower()
    suffix = path.suffix.lower()
    findings: List[Tuple[int, str]] = []
    if suffix in {".inc", ".conf", ".ucl"} or "controller" in name or "rspamd" in name:
        findings.extend(_scan_ucl(text))
    if (
        suffix in {".yml", ".yaml"}
        or "compose" in name
        or "dockerfile" in name
        or suffix == ".env"
        or name.endswith(".envfile")
    ):
        findings.extend(_scan_compose_or_dockerfile(text))
    if not findings and suffix not in {".inc", ".conf", ".ucl", ".yml", ".yaml", ".env"}:
        # Best-effort: still try UCL scan for unknown extensions.
        findings.extend(_scan_ucl(text))
        findings.extend(_scan_compose_or_dockerfile(text))
    return _filter_suppressed(text.splitlines(), findings)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file> ...]", file=sys.stderr)
        return 2
    files_with_findings = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            continue
        findings = scan_file(p)
        if not findings:
            continue
        files_with_findings += 1
        for ln, msg in findings:
            print(f"{p}:{ln}:{msg}")
    return min(files_with_findings, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
