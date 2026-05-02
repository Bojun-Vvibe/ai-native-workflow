#!/usr/bin/env python3
"""Detect Samba share definitions that are world-writable and
unauthenticated.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"[#;]\s*smb-public-write-allowed", re.IGNORECASE)

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _]*?)\s*=\s*(.*?)\s*$")

YES_TOKENS = {"yes", "true", "1", "on"}
NO_TOKENS = {"no", "false", "0", "off"}

SKIP_SECTIONS = {"global", "printers", "homes"}


def _is_yes(v: str) -> bool:
    return v.strip().lower() in YES_TOKENS


def _is_no(v: str) -> bool:
    return v.strip().lower() in NO_TOKENS


class Section:
    __slots__ = ("name", "line", "kv", "kv_lines")

    def __init__(self, name: str, line: int) -> None:
        self.name = name
        self.line = line
        self.kv: Dict[str, str] = {}
        self.kv_lines: Dict[str, int] = {}

    def get(self, key: str) -> Optional[str]:
        return self.kv.get(key.lower().replace(" ", ""))

    def has(self, key: str) -> bool:
        return key.lower().replace(" ", "") in self.kv

    def line_of(self, key: str) -> int:
        return self.kv_lines.get(key.lower().replace(" ", ""), self.line)


def _strip_comment(raw: str) -> str:
    # Samba treats both ; and # as comment leaders, but only at the
    # start of a logical token. Be conservative: only strip when the
    # comment char is preceded by whitespace or at column 0.
    out = []
    in_ws = True
    for ch in raw:
        if ch in (";", "#") and in_ws:
            break
        out.append(ch)
        in_ws = ch.isspace()
    return "".join(out)


def parse(source: str) -> List[Section]:
    sections: List[Section] = []
    current: Optional[Section] = None
    for i, raw in enumerate(source.splitlines(), start=1):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        m = SECTION_RE.match(line)
        if m:
            current = Section(m.group(1).strip().lower(), i)
            sections.append(current)
            continue
        if current is None:
            continue
        m = KV_RE.match(line)
        if m:
            key = m.group(1).strip().lower().replace(" ", "")
            val = m.group(2).strip()
            current.kv[key] = val
            current.kv_lines[key] = i
    return sections


def _is_writable(sec: Section) -> Tuple[bool, int]:
    for key in ("writable", "writeable"):
        if sec.has(key) and _is_yes(sec.get(key) or ""):
            return True, sec.line_of(key)
    if sec.has("readonly"):
        if _is_no(sec.get("readonly") or ""):
            return True, sec.line_of("readonly")
    return False, sec.line


def _is_guest(sec: Section) -> Tuple[bool, int]:
    for key in ("guestok", "public"):
        if sec.has(key) and _is_yes(sec.get(key) or ""):
            return True, sec.line_of(key)
    return False, sec.line


def _has_access_restriction(sec: Section) -> bool:
    if sec.has("validusers") and (sec.get("validusers") or "").strip():
        return True
    if sec.has("hostsallow") and (sec.get("hostsallow") or "").strip():
        return True
    if sec.has("allowhosts") and (sec.get("allowhosts") or "").strip():
        return True
    fu = sec.get("forceuser")
    if fu and fu.strip().lower() not in {"nobody", "guest"}:
        return True
    return False


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    sections = parse(source)

    global_sec: Optional[Section] = None
    for s in sections:
        if s.name == "global":
            global_sec = s
            break

    has_writable_guest = False

    for s in sections:
        if s.name in SKIP_SECTIONS:
            continue
        guest, gline = _is_guest(s)
        if not guest:
            continue
        writable, wline = _is_writable(s)
        if not writable:
            continue
        if _has_access_restriction(s):
            continue
        has_writable_guest = True
        findings.append((
            max(gline, wline),
            (
                f"share [{s.name}] is guest-accessible and writable with no "
                "valid users / hosts allow / non-nobody force user — "
                "world-writable unauthenticated SMB share"
            ),
        ))

    if global_sec is not None and has_writable_guest:
        m2g = global_sec.get("maptoguest")
        if m2g and m2g.strip().lower() == "baduser":
            findings.append((
                global_sec.line_of("maptoguest"),
                (
                    "[global] map to guest = bad user combined with a writable "
                    "guest-ok share silently maps every failed login to guest"
                ),
            ))

    findings.sort(key=lambda x: x[0])
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("smb.conf", "*.smb.conf", "*.conf"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
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
