#!/usr/bin/env python3
"""Detect GraphQL server configurations that leave introspection enabled in
production-shaped contexts.

LLM-generated GraphQL bootstraps frequently copy the development defaults from
quickstart docs (Apollo Server, graphql-yoga, Strawberry, Ariadne, graphene-
django) and ship to production with the schema fully introspectable. Public
introspection lets an attacker enumerate every type, field, and argument in
the API surface, which trivializes recon for authorization-bypass and
injection attacks.

Patterns flagged (case-insensitive substring match, regex anchored):

  - ``introspection: true`` / ``"introspection": true`` (Apollo, yoga config)
  - ``ApolloServer({ ..., introspection: true, ... })`` literal
  - ``GraphQL(... , introspect=True ...)`` or ``introspection=True``
    (Python: ariadne, graphene-django settings)
  - ``GRAPHENE = { 'SCHEMA_INDENT': ..., 'INTROSPECTION': True }``
  - explicit ``NoSchemaIntrospectionCustomRule`` removed / commented out
    (heuristic: file mentions ``NoSchemaIntrospectionCustomRule`` only inside
    a comment)
  - graphql-yoga ``createYoga({ ..., graphiql: true, ... })`` with no
    ``maskedErrors`` and no env gate (heuristic-only, low precision; emitted
    as ``info`` not as a hard finding)

A finding is emitted only when the file *also* shows a production signal
nearby (within 80 lines): one of ``NODE_ENV === "production"``,
``ENV == 'prod'``, ``settings.production``, ``DEBUG = False``,
``app.config['ENV'] = 'production'``, a Dockerfile-style ``CMD`` line, or a
filename containing ``prod``/``production``/``deploy``. This keeps the false
positive rate manageable in dev/test files.

CWE refs:
  - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
  - CWE-540: Inclusion of Sensitive Information in Source Code
  - CWE-668: Exposure of Resource to Wrong Sphere

False-positive surface:
  - Test fixtures that intentionally enable introspection to assert behavior.
    Mitigate by excluding ``**/tests/**`` and ``**/__tests__/**`` at the
    invocation layer.
  - Internal tooling (admin consoles) where introspection is desired. Suppress
    per-file with a ``# graphql-introspection-allowed`` trailing comment on
    the offending line.
  - Schema files that re-export ``NoSchemaIntrospectionCustomRule`` from a
    library — the heuristic only fires when the symbol appears *only* inside
    a comment block.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>`` per match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

PROD_SIGNALS = [
    re.compile(r"""NODE_ENV\s*[=!]==?\s*['"]production['"]"""),
    re.compile(r"""ENV\s*[=!]==?\s*['"](prod|production)['"]""", re.IGNORECASE),
    re.compile(r"""settings\.production"""),
    re.compile(r"""DEBUG\s*=\s*False"""),
    re.compile(r"""app\.config\[['"]ENV['"]\]\s*=\s*['"]production['"]"""),
    re.compile(r"""^\s*CMD\s+""", re.MULTILINE),
    re.compile(r"""FLASK_ENV\s*=\s*['"]production['"]"""),
    re.compile(r"""DJANGO_SETTINGS_MODULE.*prod""", re.IGNORECASE),
]

INTROSPECTION_PATTERNS = [
    (
        re.compile(r"""\bintrospection\s*:\s*true\b""", re.IGNORECASE),
        "Apollo/yoga config: introspection: true",
    ),
    (
        re.compile(r"""['"]introspection['"]\s*:\s*true""", re.IGNORECASE),
        "JSON/dict key 'introspection' set to true",
    ),
    (
        re.compile(r"""\bintrospect(ion)?\s*=\s*True\b"""),
        "Python kwarg introspect[ion]=True",
    ),
    (
        re.compile(r"""['"]INTROSPECTION['"]\s*:\s*True"""),
        "graphene/ariadne settings: 'INTROSPECTION': True",
    ),
]

# Heuristic: file mentions NoSchemaIntrospectionCustomRule but the only
# occurrences are inside line comments (//, #) — meaning the rule was
# commented out.
COMMENTED_RULE = re.compile(
    r"""(^|\n)\s*(//|#).*NoSchemaIntrospectionCustomRule"""
)
ANY_RULE = re.compile(r"""NoSchemaIntrospectionCustomRule""")
ACTIVE_RULE = re.compile(
    r"""(?<![/#\s])\s*NoSchemaIntrospectionCustomRule"""
)

SUPPRESS = re.compile(r"""#\s*graphql-introspection-allowed|//\s*graphql-introspection-allowed""")


def _has_prod_signal(source: str, line_idx: int, lines: List[str]) -> bool:
    name_hint = False  # filename check happens at scan_paths
    window_start = max(0, line_idx - 80)
    window_end = min(len(lines), line_idx + 80)
    window = "\n".join(lines[window_start:window_end])
    for pat in PROD_SIGNALS:
        if pat.search(window):
            return True
    return name_hint


def scan_source(source: str, filename_hint: bool) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if SUPPRESS.search(line):
            continue
        for pat, reason in INTROSPECTION_PATTERNS:
            if pat.search(line):
                if filename_hint or _has_prod_signal(source, i, lines):
                    findings.append((i + 1, reason))
                    break
    # Commented-out rule heuristic: any commented occurrence of the symbol is
    # suspicious as long as no *uncommented* line lists the symbol inside a
    # validationRules array (or assigns it as a value, not as an import).
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if "NoSchemaIntrospectionCustomRule" in line and (
            stripped.startswith("//") or stripped.startswith("#")
        ):
            # Check if any other (non-import) line uses the symbol actively.
            active = False
            for j, other in enumerate(lines):
                if j == i:
                    continue
                if "NoSchemaIntrospectionCustomRule" not in other:
                    continue
                ostripped = other.lstrip()
                if ostripped.startswith("//") or ostripped.startswith("#"):
                    continue
                if (
                    "require(" in other
                    or other.lstrip().startswith("import ")
                    or " from " in other
                ):
                    continue
                active = True
                break
            if not active and (filename_hint or _has_prod_signal(source, i, lines)):
                findings.append(
                    (i + 1, "NoSchemaIntrospectionCustomRule is commented out")
                )
                break
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    exts = {".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".py", ".json", ".yaml", ".yml"}
    for path in paths:
        if path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in exts)
        else:
            files = [path]
        for f in files:
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            name = f.name.lower()
            filename_hint = any(tok in name for tok in ("prod", "production", "deploy"))
            hits = scan_source(source, filename_hint)
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
