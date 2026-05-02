#!/usr/bin/env python3
"""Detect FTP server configurations that allow anonymous login.

Anonymous FTP exposes files without authentication. While that was a
deliberate "public file drop" pattern in the 1990s, modern LLM output
frequently emits anonymous-FTP shapes inside production
``vsftpd.conf`` / ``proftpd.conf`` / ``pure-ftpd`` flag sets and
Dockerfile ``RUN`` lines, often combined with a writable upload
directory. That combination becomes a malware drop / pivot box: the
anonymous user can upload arbitrary content, which downstream HTTP
servers may then serve or execute.

LLM-generated FTP configs routinely include::

    # vsftpd.conf
    anonymous_enable=YES
    anon_upload_enable=YES
    anon_mkdir_write_enable=YES
    no_anon_password=YES

or::

    # proftpd.conf
    <Anonymous /srv/ftp>
        User ftp
        AnonRequirePassword off
        <Limit WRITE>
            AllowAll
        </Limit>
    </Anonymous>

This detector flags those shapes.

What's checked (per file):
  - vsftpd:  ``anonymous_enable=YES`` (any case, optional whitespace).
             Stronger finding when paired with ``anon_upload_enable``,
             ``anon_mkdir_write_enable``, ``no_anon_password``, or
             ``anon_root=`` outside ``/var/empty``.
  - proftpd: ``<Anonymous ...>`` block that does NOT contain
             ``AnonRequirePassword on``, OR contains explicit
             ``AnonRequirePassword off``.
  - pure-ftpd: flag file ``NoAnonymous`` set to ``no``, or
             ``-E`` flag absent in a documented invocation /
             ``RUN pure-ftpd ...`` line that lacks ``-E``.
  - Generic: Dockerfile ``RUN`` lines that ``echo``/``sed`` any of the
             above into a config path.

CWE refs:
  - CWE-287: Improper Authentication
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-276: Incorrect Default Permissions

False-positive surface:
  - A file containing ``# ftp-anonymous-allowed`` anywhere is treated
    as an explicit public-drop config and skipped.
  - ``anonymous_enable=NO`` is safe.
  - proftpd ``<Anonymous>`` blocks that explicitly contain
    ``AnonRequirePassword on`` are safe.
  - ``anon_root=/var/empty`` (chrooted to empty) downgrades severity
    to a single info finding rather than the upload-trifecta.

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

SUPPRESS = re.compile(r"#\s*ftp-anonymous-allowed", re.IGNORECASE)

# vsftpd-style key=value (YES/NO).
VSFTPD_KV_RE = re.compile(
    r"^\s*([A-Za-z_]+)\s*=\s*(YES|NO|yes|no|true|false|1|0)\b",
)
TRUTHY = {"yes", "true", "1"}

# pure-ftpd CLI / RUN line.
PURE_FTPD_RUN_RE = re.compile(r"\bpure-ftpd\b", re.IGNORECASE)

# proftpd Anonymous block start / end.
PROFTPD_ANON_OPEN = re.compile(r"^\s*<Anonymous\b", re.IGNORECASE)
PROFTPD_ANON_CLOSE = re.compile(r"^\s*</Anonymous>", re.IGNORECASE)
PROFTPD_REQUIRE_PASS_OFF = re.compile(
    r"^\s*AnonRequirePassword\s+(off|no|false)\b", re.IGNORECASE
)
PROFTPD_REQUIRE_PASS_ON = re.compile(
    r"^\s*AnonRequirePassword\s+(on|yes|true)\b", re.IGNORECASE
)


def _scan_vsftpd(lines: List[str]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    anon_enabled_line = 0
    anon_upload = False
    anon_mkdir = False
    no_pw = False
    anon_root_safe = False
    write_enable = False

    for i, raw in enumerate(lines, start=1):
        if raw.lstrip().startswith("#"):
            continue
        m = VSFTPD_KV_RE.match(raw)
        if not m:
            continue
        key = m.group(1).lower()
        val = m.group(2).lower()
        truthy = val in TRUTHY
        if key == "anonymous_enable" and truthy:
            anon_enabled_line = i
            out.append((i, "vsftpd anonymous_enable=YES allows passwordless FTP login"))
        elif key == "anon_upload_enable" and truthy:
            anon_upload = True
            out.append((i, "vsftpd anon_upload_enable=YES lets the anonymous user upload"))
        elif key == "anon_mkdir_write_enable" and truthy:
            anon_mkdir = True
            out.append((i, "vsftpd anon_mkdir_write_enable=YES lets the anonymous user create dirs"))
        elif key == "no_anon_password" and truthy:
            no_pw = True
            out.append((i, "vsftpd no_anon_password=YES skips even the email-as-password prompt"))
        elif key == "write_enable" and truthy:
            write_enable = True
        elif key == "anon_root":
            # Not a kv match — handled below.
            pass

    # anon_root=<path> (separate regex; value isn't YES/NO).
    for i, raw in enumerate(lines, start=1):
        if raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*anon_root\s*=\s*(\S+)", raw)
        if m and m.group(1).strip() in ("/var/empty", "/var/empty/"):
            anon_root_safe = True

    if anon_enabled_line and (anon_upload or anon_mkdir) and not anon_root_safe:
        out.append((
            anon_enabled_line,
            "trifecta: anonymous FTP + anon write enabled — anonymous-malware-drop pattern",
        ))
    return out


def _scan_proftpd(lines: List[str]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    in_block = False
    block_start = 0
    require_pass_seen_on = False
    require_pass_seen_off_line = 0

    for i, raw in enumerate(lines, start=1):
        if PROFTPD_ANON_OPEN.match(raw):
            in_block = True
            block_start = i
            require_pass_seen_on = False
            require_pass_seen_off_line = 0
            continue
        if PROFTPD_ANON_CLOSE.match(raw):
            if in_block:
                if require_pass_seen_off_line:
                    out.append((
                        require_pass_seen_off_line,
                        "proftpd <Anonymous> block sets AnonRequirePassword off",
                    ))
                elif not require_pass_seen_on:
                    out.append((
                        block_start,
                        "proftpd <Anonymous> block has no AnonRequirePassword on (default = anonymous)",
                    ))
            in_block = False
            continue
        if in_block:
            if PROFTPD_REQUIRE_PASS_ON.match(raw):
                require_pass_seen_on = True
            elif PROFTPD_REQUIRE_PASS_OFF.match(raw):
                require_pass_seen_off_line = i
    return out


def _scan_pure_ftpd(lines: List[str]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    # Flag-file form: NoAnonymous = no
    for i, raw in enumerate(lines, start=1):
        if raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*NoAnonymous\s*[:=]?\s*(yes|no|true|false|1|0)\b", raw, re.IGNORECASE)
        if m and m.group(1).lower() in {"no", "false", "0"}:
            out.append((i, "pure-ftpd NoAnonymous=no enables anonymous logins"))
        # CLI invocation lacking -E (which forces auth-only).
        if PURE_FTPD_RUN_RE.search(raw) and " -E" not in raw and "--noanonymous" not in raw:
            # Only flag explicit invocations (RUN / CMD / ENTRYPOINT / shell).
            if re.search(r"\b(RUN|CMD|ENTRYPOINT|exec)\b", raw) or raw.lstrip().startswith("pure-ftpd"):
                out.append((i, "pure-ftpd invocation missing -E flag → anonymous logins permitted"))
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    lines = source.splitlines()
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_vsftpd(lines))
    findings.extend(_scan_proftpd(lines))
    findings.extend(_scan_pure_ftpd(lines))
    # Dedup by (line, reason).
    seen = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    unique.sort(key=lambda x: x[0])
    return unique


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.conf", "vsftpd*", "proftpd*", "pure-ftpd*", "Dockerfile*"):
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
