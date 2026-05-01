#!/usr/bin/env python3
"""Detect Rails strong-parameter handlers that accept arbitrary attributes,
defeating the mass-assignment guard that strong_params is supposed to provide.

LLM-generated Rails controllers frequently shortcut the strong_params dance
by writing one of:

  - ``params.permit!``                       (whitelists every key)
  - ``params.require(:user).permit!``        (same, scoped)
  - ``params[:user].permit!``                (same, alt syntax)
  - ``params.permit(params.keys)``           (dynamic key list = no guard)
  - ``params.permit(*params.keys)``          (same, splatted)
  - ``params.require(:foo).permit(params[:foo].keys)``
  - direct ``Model.new(params[:foo])`` without ``.permit`` at all
  - direct ``Model.update(params[:foo])`` without ``.permit``
  - direct ``Model.create(params[:foo])`` without ``.permit``

Any of these allow an attacker to set sensitive attributes (``admin``,
``role``, ``stripe_customer_id``, ``confirmed_at``, etc.) by adding them to
the request body — the canonical mass-assignment vulnerability that
strong_params was introduced to prevent.

CWE refs:
  - CWE-915: Improperly Controlled Modification of Dynamically-Determined
    Object Attributes
  - CWE-284: Improper Access Control

False-positive surface:
  - Internal admin actions where every attribute really should be writable.
    Suppress with a trailing ``# mass-assignment-allowed`` comment on the
    offending line.
  - Test factories / seed scripts that use ``Model.create(attrs)`` with a
    locally-built hash. Mitigate by excluding ``spec/``, ``test/``,
    ``db/seeds*``, ``db/fixtures/`` at the invocation layer.
  - DSL-style code where ``params`` is a local variable, not the Rails
    request hash. The detector requires the literal token ``params`` and
    cannot distinguish; suppress per line if needed.

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

SUPPRESS = re.compile(r"#\s*mass-assignment-allowed")

# Patterns ordered most-specific first.
PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(r"\bparams\s*(\.[a-zA-Z_][\w]*\([^)]*\))*\s*\.permit!"),
        "params.permit! whitelists every attribute",
    ),
    (
        re.compile(r"\bparams\s*\[\s*:[\w]+\s*\]\s*\.permit!"),
        "params[:x].permit! whitelists every attribute",
    ),
    (
        re.compile(r"\.permit\s*\(\s*\*?\s*params(\[[^\]]+\])?\.keys\s*\)"),
        ".permit(params[...].keys) defeats the strong-param allowlist",
    ),
    (
        re.compile(
            r"(?:[A-Z][\w:]*|@?[a-z_][\w]*(?:\.[a-z_][\w]*)*)\.(?:new|create|create!|update|update!|update_attributes|assign_attributes)\s*\(\s*params\s*\[\s*:[\w]+\s*\]\s*\)"
        ),
        "<receiver>.<method>(params[:x]) bypasses strong_params entirely",
    ),
    (
        re.compile(
            r"(?:[A-Z][\w:]*|@?[a-z_][\w]*(?:\.[a-z_][\w]*)*)\.(?:new|create|create!|update|update!|update_attributes|assign_attributes)\s*\(\s*params\s*\)"
        ),
        "<receiver>.<method>(params) bypasses strong_params entirely",
    ),
]


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    seen: set[Tuple[int, str]] = set()
    for i, line in enumerate(source.splitlines(), start=1):
        if SUPPRESS.search(line):
            continue
        # Strip Ruby comments to avoid matching inside `# ...`
        code = re.sub(r"(?<!:)#.*$", "", line)
        for pat, reason in PATTERNS:
            if pat.search(code):
                key = (i, reason)
                if key not in seen:
                    seen.add(key)
                    findings.append(key)
                break  # one finding per line is enough
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for path in paths:
        if path.is_dir():
            files = sorted(path.rglob("*.rb"))
        else:
            files = [path]
        for f in files:
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            hits = scan_source(source)
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
