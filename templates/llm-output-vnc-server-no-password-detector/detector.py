#!/usr/bin/env python3
"""Detect VNC server invocations / configs that expose a desktop with
no authentication.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*vnc-no-auth-allowed", re.IGNORECASE)

VNC_TOKENS = (
    "x11vnc",
    "vncserver",
    "Xvnc",
    "tigervnc",
    "tightvncserver",
    "tigervncserver",
)

# Match any VNC server token as a whole word (allow path prefix).
VNC_TOKEN_RE = re.compile(
    r"(?:^|[\s\"'`/=\[\(])(" + "|".join(re.escape(t) for t in VNC_TOKENS) + r")\b"
)

NOPW_FLAG_RE = re.compile(r"(?<!\S)(?:-nopw|-noauth)\b")
PASSWD_DEVNULL_RE = re.compile(r"-passwdfile\s+/dev/null\b")
SECTYPES_NONE_RE = re.compile(
    r"(?:-SecurityTypes\s+|SecurityTypes\s*=\s*)none\b", re.IGNORECASE
)
LOCALHOST_FLAG_RE = re.compile(r"(?<!\S)-localhost(?:\s+yes\b|\b)", re.IGNORECASE)
RFBPORT_LOOPBACK_RE = re.compile(
    r"-rfbport\s+(?:127\.0\.0\.1|::1|localhost)\b", re.IGNORECASE
)

# Env-var style misconfigurations.
VNC_PW_EMPTY_RE = re.compile(
    r"""^\s*(?:-\s*|ENV\s+)?(?:VNC_PW|VNC_PASSWORD)\s*[:=]\s*(['"]?)\1\s*$"""
)
VNC_NO_PW_TRUE_RE = re.compile(
    r"""^\s*(?:-\s*|ENV\s+)?VNC_NO_PASSWORD\s*[:=]\s*(['"]?)(?:1|true|yes)\1\s*$""",
    re.IGNORECASE,
)
VNC_PORT_EXPOSE_RE = re.compile(r"5900|5901|5902|5903")

CONFIG_HINT_NAMES = {"config", "tigervnc.conf"}
CONFIG_HINT_RE = re.compile(r"(?:^|[_\-\.])(tigervnc|vnc)(?:[_\-\.]|$)", re.IGNORECASE)


def _is_local_only(line: str) -> bool:
    return bool(LOCALHOST_FLAG_RE.search(line) or RFBPORT_LOOPBACK_RE.search(line))


def scan(source: str, filename: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    is_config_file = (
        filename in CONFIG_HINT_NAMES
        or filename.endswith(".tigervnc")
        or filename.endswith("tigervnc.conf")
        or (CONFIG_HINT_RE.search(filename) is not None and "." not in filename)
    )

    saw_vnc_image = False
    vnc_image_re = re.compile(
        r"(?:image\s*:\s*[\"']?[^\s\"']*"
        r"(?:tigervnc|x11vnc|novnc|vnc-server|vnc[-_]?server|"
        r"dorowu/ubuntu-desktop-lxde-vnc|consol/[^\s\"']*vnc|"
        r"ubuntu-xfce-vnc|ubuntu-desktop-lxde-vnc)"
        r"|FROM\s+\S*vnc\S*"
        r"|FROM\s+consol/[^\s]*vnc[^\s]*)",
        re.IGNORECASE,
    )
    file_has_vnc_port = bool(VNC_PORT_EXPOSE_RE.search(source))
    file_has_vnc_image = bool(vnc_image_re.search(source))

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        # Strip trailing inline comments for shells/Dockerfiles only when
        # # is preceded by whitespace; keep YAML/HCL alone for safety.
        scan_line = line

        if vnc_image_re.search(scan_line):
            saw_vnc_image = True

        # Rule 3: standalone TigerVNC config file with SecurityTypes=None
        if is_config_file and SECTYPES_NONE_RE.search(scan_line):
            findings.append((
                i,
                "TigerVNC config sets SecurityTypes=None — desktop exposed with no auth",
            ))
            continue

        # Rule 1 / 2: invocation lines must mention a VNC server token
        if VNC_TOKEN_RE.search(scan_line):
            local_only = _is_local_only(scan_line)
            if NOPW_FLAG_RE.search(scan_line) and not local_only:
                findings.append((
                    i,
                    "VNC server launched with -nopw/-noauth and no -localhost — "
                    "no authentication on a network-reachable port",
                ))
                continue
            if PASSWD_DEVNULL_RE.search(scan_line) and not local_only:
                findings.append((
                    i,
                    "VNC server launched with -passwdfile /dev/null and no "
                    "-localhost — empty password file",
                ))
                continue
            if SECTYPES_NONE_RE.search(scan_line) and not local_only:
                findings.append((
                    i,
                    "VNC server launched with SecurityTypes=None and no "
                    "-localhost — no authentication",
                ))
                continue

        # Rule 4: env-var disablement near a VNC server image / port.
        if saw_vnc_image or file_has_vnc_image or file_has_vnc_port or VNC_PORT_EXPOSE_RE.search(scan_line):
            if VNC_PW_EMPTY_RE.match(scan_line):
                findings.append((
                    i,
                    "VNC container env sets VNC_PW to empty string — no password",
                ))
                continue
            if VNC_NO_PW_TRUE_RE.match(scan_line):
                findings.append((
                    i,
                    "VNC container env sets VNC_NO_PASSWORD=1/true — auth disabled",
                ))
                continue

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in (
                "*.sh",
                "*.bash",
                "Dockerfile",
                "*.Dockerfile",
                "*.yaml",
                "*.yml",
                "*.service",
                "*.conf",
                "*.tigervnc",
                "config",
            ):
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
        hits = scan(source, f.name)
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
