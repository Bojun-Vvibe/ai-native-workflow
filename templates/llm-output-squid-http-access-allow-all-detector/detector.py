#!/usr/bin/env python3
"""Detect `http_access allow all` in Squid configs (LLM-generated open proxies).

Stdlib only. Exits with the number of files containing at least one finding.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Tuple

# ACLs that, when present after `all` on the same line, do NOT narrow the rule.
# (`all` is already the universe; combining it with another universal ACL is
# still universal.) We list these so we don't accidentally treat e.g.
# `http_access allow all manager` as "narrowed" — it isn't.
WIDE_OPEN_ACLS = {"all", "manager"}


def scan_lines(lines: Iterable[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip inline comments (Squid uses `#` for comments).
        code = stripped.split("#", 1)[0].strip()
        if not code:
            continue
        tokens = code.split()
        if len(tokens) < 3:
            continue
        if tokens[0] != "http_access" or tokens[1] != "allow":
            continue
        acls = tokens[2:]
        if "all" not in acls:
            continue
        # Anything after `all` that is NOT a wide-open ACL counts as a
        # narrowing condition (Squid AND-joins ACLs on one line).
        narrowing = [a for a in acls if a not in WIDE_OPEN_ACLS]
        if narrowing:
            continue
        findings.append((lineno, line))
    return findings


def extract_squid_blocks_from_markdown(text: str) -> List[Tuple[int, str]]:
    """Yield (start_lineno_in_doc, block_text) for fenced squid/conf blocks."""
    out: List[Tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            tag = line[3:].strip().lower()
            if tag in {"squid", "conf", "squid.conf"}:
                start = i + 1
                buf: List[str] = []
                i += 1
                while i < len(lines) and not lines[i].rstrip().startswith("```"):
                    buf.append(lines[i])
                    i += 1
                out.append((start, "\n".join(buf)))
        i += 1
    return out


def scan_file(path: Path) -> List[Tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"{path}: ERROR: {exc}", file=sys.stderr)
        return []

    findings: List[Tuple[int, str]] = []
    if path.suffix.lower() in {".md", ".markdown"}:
        for offset, block in extract_squid_blocks_from_markdown(text):
            for lineno, line in scan_lines(block.splitlines()):
                findings.append((offset + lineno - 1, line))
    else:
        findings.extend(scan_lines(text.splitlines()))
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    files_with_findings = 0
    for arg in argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"{path}: ERROR: not found", file=sys.stderr)
            continue
        findings = scan_file(path)
        if findings:
            files_with_findings += 1
            for lineno, line in findings:
                print(f"{path}:{lineno}: {line}")
    return files_with_findings


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
