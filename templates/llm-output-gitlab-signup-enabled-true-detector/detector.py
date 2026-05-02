#!/usr/bin/env python3
"""Detect GitLab self-managed configurations that ship with public
sign-up enabled (``signup_enabled = true``).

Public sign-up on a self-hosted GitLab instance lets any unauthenticated
visitor create an account. On a private instance this is an
unauthenticated account-creation primitive that lets attackers fork
internal repos, open issues, abuse CI runners, and harvest project
metadata. The hardened default for an internal instance is
``signup_enabled = false``; LLM-generated ``gitlab.rb`` snippets,
Helm ``values.yaml`` files, and Docker bootstrap scripts often paste
in tutorial-style configs that flip it back on.

What's checked (per file):
  - Ruby/HCL: ``gitlab_rails['signup_enabled'] = true`` in
    ``gitlab.rb``.
  - YAML (Helm chart values): ``signup_enabled: true`` under the
    ``appConfig`` / ``gitlab`` block.
  - Dockerfile / shell: ``GITLAB_OMNIBUS_CONFIG`` env or ``echo`` /
    ``sed`` lines that set ``signup_enabled`` to true.

Accepted (not flagged):
  - ``signup_enabled = false`` / ``signup_enabled: false``.
  - Any file containing ``# gitlab-signup-allowed`` (committed test
    fixtures or instances that intentionally allow registration, e.g.
    a public community server).
  - Lines beginning with ``#``.

CWE refs:
  - CWE-284: Improper Access Control
  - CWE-269: Improper Privilege Management
  - CWE-862: Missing Authorization

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*gitlab-signup-allowed", re.IGNORECASE)

TRUTHY = {"true", "1", "yes", "on"}

# gitlab.rb (Ruby): gitlab_rails['signup_enabled'] = true
RB_RE = re.compile(
    r"""gitlab_rails\s*\[\s*['"]signup_enabled['"]\s*\]\s*=\s*([A-Za-z0-9_]+)""",
    re.IGNORECASE,
)

# Helm / YAML: signup_enabled: true
YAML_RE = re.compile(
    r"""^\s*signup_enabled\s*:\s*['"]?([A-Za-z0-9_]+)['"]?""",
    re.IGNORECASE,
)

# Shell/Dockerfile: signup_enabled=true (echo/sed/env)
SHELL_RE = re.compile(
    r"""signup_enabled\s*=\s*['"]?([A-Za-z0-9_]+)['"]?""",
    re.IGNORECASE,
)


def _normalize(val: str) -> str:
    return val.strip().strip("'\"").lower()


def _is_truthy(val: str) -> bool:
    return _normalize(val) in TRUTHY


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue

        m = RB_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"gitlab_rails['signup_enabled'] = {m.group(1)} permits public account creation")
            )
            continue

        m = YAML_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"signup_enabled: {m.group(1)} permits public account creation")
            )
            continue

        # Shell/env shape: signup_enabled=true (avoid double-reporting
        # the Ruby ``gitlab_rails['signup_enabled']`` form already
        # captured above).
        already_ruby = bool(RB_RE.search(raw))
        m = SHELL_RE.search(raw)
        if m and _is_truthy(m.group(1)) and not already_ruby:
            findings.append(
                (i, f"shell/env signup_enabled={m.group(1)} permits public account creation")
            )
            continue

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.rb", "*.yml", "*.yaml", "Dockerfile*", "*.sh", "*.env"):
                targets.extend(sorted(path.rglob(pat)))
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
