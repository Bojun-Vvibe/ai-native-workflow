#!/usr/bin/env python3
"""Detect `PermitEmptyPasswords yes` in sshd configs / shell snippets / markdown.

Stdlib only. Exit code = number of files containing >=1 finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

KEYWORD = "permitemptypasswords"

# Match `PermitEmptyPasswords yes` (case-insensitive), allowing optional
# whitespace and an optional trailing comment.
DIRECT_RE = re.compile(
    r"^\s*permitemptypasswords\s+yes\s*(?:#.*)?$",
    re.IGNORECASE,
)

# Match shell-wrapped forms commonly emitted by Dockerfiles / cloud-init:
#   echo "PermitEmptyPasswords yes" >> /etc/ssh/sshd_config
#   printf 'PermitEmptyPasswords yes\n' >> ...
#   tee -a ... <<< "PermitEmptyPasswords yes"
# We just look for the keyword + value anywhere in a line that also looks
# shell-y (contains `echo`/`printf`/`tee`/`sed`).
SHELL_HINTS = ("echo", "printf", "tee", "sed", "cat ")
SHELL_KW_RE = re.compile(
    r"permitemptypasswords[\s'\"=]+yes",
    re.IGNORECASE,
)

# Match `sed -i 's/.../PermitEmptyPasswords yes/' ...` style.
SED_RE = re.compile(
    r"sed\b.*permitemptypasswords[^/]*/\s*permitemptypasswords\s+yes",
    re.IGNORECASE,
)


def _strip_inline_comment(line: str) -> str:
    # sshd_config uses `#` for comments. Strip safely (no quoting concerns
    # for this directive's value space).
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def scan_lines(lines: Iterable[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue

        # Direct sshd_config form.
        cleaned = _strip_inline_comment(line).rstrip()
        if DIRECT_RE.match(cleaned):
            findings.append((lineno, line))
            continue

        # Shell-wrapped append/printf form.
        low = line.lower()
        if any(h in low for h in SHELL_HINTS) and SHELL_KW_RE.search(line):
            findings.append((lineno, line))
            continue

        # sed-rewrite form.
        if SED_RE.search(line):
            findings.append((lineno, line))
            continue
    return findings


def extract_blocks_from_markdown(text: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            tag = line[3:].strip().lower()
            if tag in {"sshd_config", "sshd", "ssh", "conf", "bash", "sh", "dockerfile"}:
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
        for offset, block in extract_blocks_from_markdown(text):
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
