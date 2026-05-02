#!/usr/bin/env python3
"""Detect Jupyter Notebook / JupyterLab / Jupyter Server configuration
files (or equivalent CLI snippets) that disable both token and password
authentication, leaving the kernel as an unauthenticated remote code
execution endpoint.

Background. Jupyter ships with a randomly generated token because a
notebook server is, in effect, a remote Python REPL: anyone who can
hit the HTTP endpoint can spawn a kernel and execute arbitrary code as
the kernel user. The single most common LLM-suggested workaround for
"I keep being prompted for a token" is::

    c.ServerApp.token = ''
    c.ServerApp.password = ''

which removes both authentication paths simultaneously. Combined with
the equally common ``c.ServerApp.ip = '0.0.0.0'``, this is how Jupyter
servers end up indexed by mass scanners.

This detector is intentionally orthogonal to bind-address / TLS
detectors. Even on a "trusted" LAN, an unauthenticated kernel is a
lateral-movement primitive (sidecar containers, co-tenant pods,
forgotten port-forwards) and the misconfig is bad on its own.

What's checked (per file):
  - Python config (``jupyter_*_config.py``): assignments to
    ``c.NotebookApp.token`` / ``c.ServerApp.token`` *and*
    ``c.NotebookApp.password`` / ``c.ServerApp.password`` that are
    both empty string literals.
  - JSON config: an object with ``NotebookApp`` or ``ServerApp`` whose
    ``token`` and ``password`` are both empty strings.
  - CLI fragments: ``jupyter (notebook|lab|server) ...
    --(NotebookApp|ServerApp).token=`` AND
    ``--(NotebookApp|ServerApp).password=`` (or
    ``--ServerApp.token=''``) on the same logical command, both empty.

Findings are reported per line of the relevant assignment.

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-287: Improper Authentication
  - CWE-1188: Initialization of a Resource with an Insecure Default

False-positive surface:
  - Suppress per file with a comment ``# jupyter-open-allowed``.
  - A non-empty token or non-empty password (literal or via
    ``os.environ`` / ``os.getenv``) makes the file safe.
  - Prose mentions inside ``#``-comments are ignored.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*jupyter-open-allowed")

# Python: c.NotebookApp.token = '' / c.ServerApp.token = ""
PY_TOKEN_RE = re.compile(
    r"""^\s*c\.(?:NotebookApp|ServerApp)\.token\s*=\s*(?P<val>.+?)\s*(?:\#.*)?$""",
)
PY_PASSWORD_RE = re.compile(
    r"""^\s*c\.(?:NotebookApp|ServerApp)\.password\s*=\s*(?P<val>.+?)\s*(?:\#.*)?$""",
)

# CLI: --NotebookApp.token=  /  --ServerApp.token=''  /  --ServerApp.token ""
CLI_TOKEN_RE = re.compile(
    r"--(?:NotebookApp|ServerApp)\.token(?:\s*=\s*|\s+)(?P<val>(?:'[^']*'|\"[^\"]*\"|\S*))",
)
CLI_PASSWORD_RE = re.compile(
    r"--(?:NotebookApp|ServerApp)\.password(?:\s*=\s*|\s+)(?P<val>(?:'[^']*'|\"[^\"]*\"|\S*))",
)


def _is_empty_literal(val: str) -> bool:
    """True iff ``val`` is an empty string literal (``''`` / ``""``)."""
    v = val.strip()
    return v in ("''", '""', "u''", 'u""', "''", '""')


def _is_env_lookup(val: str) -> bool:
    v = val.strip()
    return (
        "os.environ" in v
        or "os.getenv" in v
        or "getenv(" in v
        or "environ[" in v
    )


def _scan_python(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    token_empty_line: Optional[int] = None
    token_nonempty = False
    password_empty_line: Optional[int] = None
    password_nonempty = False

    for i, raw in enumerate(source.splitlines(), start=1):
        # Drop trailing comment for matching, but keep raw for line.
        line = raw
        # Skip pure-comment lines.
        if line.lstrip().startswith("#"):
            continue

        m = PY_TOKEN_RE.match(line)
        if m:
            val = m.group("val")
            if _is_empty_literal(val):
                if token_empty_line is None:
                    token_empty_line = i
            elif _is_env_lookup(val) or val.strip() not in ("None", "none"):
                token_nonempty = True
            continue

        m = PY_PASSWORD_RE.match(line)
        if m:
            val = m.group("val")
            if _is_empty_literal(val):
                if password_empty_line is None:
                    password_empty_line = i
            elif _is_env_lookup(val) or val.strip() not in ("None", "none"):
                password_nonempty = True
            continue

    # Require BOTH to be empty (or empty + missing) AND neither to be
    # overridden later. We only flag when we can prove both are empty.
    if (
        token_empty_line is not None
        and password_empty_line is not None
        and not token_nonempty
        and not password_nonempty
    ):
        line = min(token_empty_line, password_empty_line)
        findings.append((
            line,
            "c.ServerApp.token set to empty string and no password "
            "configured — kernel is unauthenticated RCE",
        ))
    return findings


def _scan_cli(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw
        if "jupyter" not in line.lower():
            continue
        tok = CLI_TOKEN_RE.search(line)
        pw = CLI_PASSWORD_RE.search(line)
        if not tok or not pw:
            continue
        tok_val = tok.group("val").strip()
        pw_val = pw.group("val").strip()
        # `--token=` (no value) or `--token=''` / `--token=""`.
        empty_tok = tok_val in ("", "''", '""')
        empty_pw = pw_val in ("", "''", '""')
        if empty_tok and empty_pw:
            findings.append((
                i,
                "jupyter CLI passes empty token and empty password — "
                "kernel is unauthenticated RCE",
            ))
    return findings


def _scan_json(source: str) -> List[Tuple[int, str]]:
    try:
        data = json.loads(source)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    findings: List[Tuple[int, str]] = []
    for key in ("NotebookApp", "ServerApp"):
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        token = section.get("token", None)
        password = section.get("password", None)
        if token == "" and password == "":
            findings.append((
                1,
                f"{key}.token and {key}.password both set to empty "
                "string — kernel is unauthenticated RCE",
            ))
    return findings


def scan(source: str, path: Optional[Path] = None) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    findings: List[Tuple[int, str]] = []
    suffix = path.suffix.lower() if path is not None else ""
    if suffix == ".json":
        findings.extend(_scan_json(source))
    else:
        findings.extend(_scan_python(source))
        findings.extend(_scan_cli(source))
    # Deduplicate on (line, reason).
    seen = set()
    out: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.py", "*.json", "*.sh", "*.conf", "Dockerfile"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source, f)
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
