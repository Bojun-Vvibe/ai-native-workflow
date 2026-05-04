#!/usr/bin/env python3
"""Detect Gotify ``config.yml`` files that ship the bootstrap admin
account with the default / weak password.

Gotify (https://gotify.net) is a self-hosted push-notification server.
On first boot it reads ``config.yml`` (or env vars
``GOTIFY_DEFAULTUSER_NAME`` / ``GOTIFY_DEFAULTUSER_PASS``) and creates
an admin account. The shipped example uses::

    defaultuser:
      name: admin
      pass: admin

Anyone who can reach the HTTP listener and POSTs to
``/login`` with those creds gets full admin: create / delete users,
read every message in every application stream, and rotate every
client / application token.

LLM-generated docker-compose / helm values regularly pin those
defaults verbatim because they are the literal example in the README.

What this detector flags (per file):

  - ``defaultuser.pass`` set to one of a curated list of weak /
    placeholder values: ``admin``, ``password``, ``changeme``,
    ``gotify``, ``letmein``, ``123456``, empty string, ``"<TODO>"``,
    ``"<change-me>"``, etc.
  - ``defaultuser.name: admin`` paired with a ``defaultuser.pass``
    that is shorter than 8 characters.
  - The whole ``defaultuser`` block present with ``name`` set but
    ``pass`` missing entirely (Gotify falls back to the default
    "admin").
  - ``passstrength: 0`` (or any value < 8): Gotify's bcrypt cost
    knob; ``0`` causes Gotify to use the *default cost*, but in
    older releases ``0`` literally means "no hashing" — flagged
    defensively.

Suppression:
  - Add a top-of-file comment ``# gotify-default-admin-allowed``.

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1392: Use of Default Credentials

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*gotify-default-admin-allowed")

WEAK_PASSWORDS = {
    "",
    "admin",
    "administrator",
    "changeme",
    "change-me",
    "default",
    "gotify",
    "letmein",
    "password",
    "passwd",
    "pass",
    "root",
    "test",
    "12345",
    "123456",
    "1234567",
    "12345678",
    "qwerty",
    "secret",
    "<todo>",
    "<change-me>",
    "<changeme>",
    "<placeholder>",
    "TODO",
}


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(val: str) -> str:
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _parse_defaultuser(lines: List[str]) -> Optional[Tuple[int, int, dict]]:
    """Return (start_line_0, end_line_0, fields) for the ``defaultuser:``
    mapping if present (top-level)."""
    for i, raw in enumerate(lines):
        s = _strip_comment(raw)
        if not s.strip():
            continue
        if _indent(raw) == 0 and re.match(r"^defaultuser\s*:\s*$", s):
            base = _indent(raw)
            fields: dict = {}
            j = i + 1
            child_indent: Optional[int] = None
            end = i
            while j < len(lines):
                rj = lines[j]
                if not rj.strip() or _strip_comment(rj).strip() == "":
                    j += 1
                    continue
                ij = _indent(rj)
                if ij <= base:
                    break
                if child_indent is None:
                    child_indent = ij
                if ij == child_indent:
                    sj = _strip_comment(rj)
                    m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", sj)
                    if m:
                        fields[m.group(1).lower()] = (j + 1, m.group(2).strip())
                end = j
                j += 1
            return i, end, fields
    return None


def _find_passstrength(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Return (line_no_1based, value) for top-level passstrength."""
    for i, raw in enumerate(lines):
        s = _strip_comment(raw)
        m = re.match(r"^\s*passstrength\s*:\s*(\S+)", s)
        if m and _indent(raw) == 0:
            try:
                return i + 1, int(m.group(1))
            except ValueError:
                return None
    return None


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()

    # Relevance gate: must look like a Gotify config.
    txt = "\n".join(lines)
    looks_gotify = (
        re.search(r"(?m)^defaultuser\s*:", txt) is not None
        or re.search(r"(?mi)^server\s*:", txt) is not None
        and re.search(r"(?mi)\bpassstrength\b", txt) is not None
    )
    if not looks_gotify:
        return findings

    parsed = _parse_defaultuser(lines)
    if parsed is not None:
        _, _, fields = parsed
        name_entry = fields.get("name")
        pass_entry = fields.get("pass")
        name_value = _unquote(name_entry[1]) if name_entry else ""
        if pass_entry:
            line_no, raw_val = pass_entry
            val = _unquote(raw_val)
            low = val.strip().lower()
            if low in WEAK_PASSWORDS:
                findings.append(
                    (line_no, f"defaultuser.pass={val!r} is a known weak/default credential")
                )
            elif name_value.lower() == "admin" and len(val) < 8:
                findings.append(
                    (line_no, f"defaultuser.name=admin paired with short pass (len={len(val)} < 8)")
                )
        else:
            # No pass key → Gotify uses bundled default "admin".
            if name_entry:
                findings.append(
                    (name_entry[0], "defaultuser.name set but defaultuser.pass missing — falls back to 'admin'")
                )

    ps = _find_passstrength(lines)
    if ps is not None:
        ln, val = ps
        if val < 8:
            findings.append(
                (ln, f"passstrength={val} is below recommended bcrypt cost 10 (minimum 8)")
            )

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.yml", "*.yaml"):
                targets.extend(sorted(path.rglob(ext)))
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
