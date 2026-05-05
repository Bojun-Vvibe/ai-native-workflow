#!/usr/bin/env python3
"""
llm-output-octoprint-access-control-disabled-detector

Flags OctoPrint configurations that disable the access control system,
which exposes the full G-code / printer-control API to any anonymous
HTTP client. OctoPrint's `accessControl.enabled: false` (config.yaml)
or `OCTOPRINT_ACCESS_CONTROL_ENABLED=false` (templated images) skips
the first-run admin-account wizard and grants every visitor
administrator privileges, including the ability to upload arbitrary
firmware, send raw G-code (which can drive a heater past its thermal
runaway protection), and read/write files on the host filesystem
through the file manager plugin.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-284: Improper Access Control.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
config.yaml, *.yaml, *.yml, *.conf, *.ini, Dockerfile,
docker-compose.*, *.sh, *.bash, *.service, *.env).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `#` / `;`
comment lines):

1. config.yaml block under `accessControl:` containing `enabled: false`
   (we use a small two-pass scan: track when we are inside an
   `accessControl:` block by indentation, and flag the `enabled: false`
   child line).
2. Inline / flow-style YAML `accessControl: {enabled: false ...}`.
3. CLI flag `--no-access-control` to `octoprint serve` (Dockerfile
   CMD/ENTRYPOINT, shell wrapper, systemd ExecStart, k8s args).
4. Env-var override `OCTOPRINT_ACCESS_CONTROL_ENABLED=false` used by
   the popular `octoprint/octoprint` and `outpostzero/octoprint`
   templated images.
5. config.yaml top-level `firstRun: false` paired with a missing
   `accessControl:` section in the same file (the wizard is skipped
   AND nothing replaces it — pure anonymous admin).

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Inline / flow-style: accessControl: {enabled: false}
_INLINE_DISABLED = re.compile(
    r"""(?im)\baccessControl\s*:\s*\{[^}]*\benabled\s*:\s*false\b[^}]*\}"""
)

# CLI flag: octoprint serve --no-access-control
_CLI_NO_AC = re.compile(
    r"""--no-access-control\b"""
)

# Env override
_ENV_OVERRIDE = re.compile(
    r"""(?im)^\s*(?:export\s+|-\s+)?OCTOPRINT_ACCESS_CONTROL_ENABLED\s*[:=]\s*["']?false["']?\b"""
)

# config.yaml block markers
_BLOCK_HEADER = re.compile(r"""^(\s*)accessControl\s*:\s*(?:#.*)?$""")
_ENABLED_FALSE_CHILD = re.compile(
    r"""^(\s+)enabled\s*:\s*false\b"""
)
_FIRSTRUN_FALSE = re.compile(
    r"""(?im)^\s*firstRun\s*:\s*false\b"""
)
_ACCESSCONTROL_ANY = re.compile(
    r"""(?im)^\s*accessControl\s*:"""
)

_COMMENT_LINE = re.compile(r"""^\s*#""")


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()

    # Pass 1: block-form accessControl.enabled = false
    in_block = False
    block_indent = -1
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue

        m_hdr = _BLOCK_HEADER.match(raw)
        if m_hdr:
            in_block = True
            block_indent = len(m_hdr.group(1))
            continue

        if in_block:
            stripped = raw.rstrip()
            if not stripped:
                continue
            # Determine indentation of this line.
            indent = len(raw) - len(raw.lstrip(" "))
            if indent <= block_indent:
                # Block ended.
                in_block = False
                block_indent = -1
            else:
                m_child = _ENABLED_FALSE_CHILD.match(raw)
                if m_child:
                    findings.append(
                        f"{path}:{lineno}: config.yaml "
                        f"`accessControl.enabled: false` disables "
                        f"OctoPrint authentication entirely "
                        f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
                    )

    # Pass 2: per-line patterns
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _INLINE_DISABLED.search(raw):
            findings.append(
                f"{path}:{lineno}: inline YAML "
                f"`accessControl: {{enabled: false}}` disables OctoPrint "
                f"auth (CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue
        if _CLI_NO_AC.search(raw):
            findings.append(
                f"{path}:{lineno}: octoprint launched with "
                f"--no-access-control (auth disabled) "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue
        if _ENV_OVERRIDE.search(raw):
            findings.append(
                f"{path}:{lineno}: "
                f"OCTOPRINT_ACCESS_CONTROL_ENABLED=false env override "
                f"templates config.yaml with auth disabled "
                f"(CWE-306/CWE-284): {raw.strip()[:160]}"
            )
            continue

    # Pass 3: firstRun:false with no accessControl section anywhere.
    if _FIRSTRUN_FALSE.search(text) and not _ACCESSCONTROL_ANY.search(text):
        for lineno, raw in enumerate(lines, start=1):
            if _COMMENT_LINE.match(raw):
                continue
            if _FIRSTRUN_FALSE.search(raw):
                findings.append(
                    f"{path}:{lineno}: `firstRun: false` ships with no "
                    f"`accessControl:` section — first-run wizard is "
                    f"skipped and nothing creates the admin account, "
                    f"leaving anonymous admin (CWE-1188/CWE-284): "
                    f"{raw.strip()[:160]}"
                )
                break

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "config.yaml",
    "config.yml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".conf", ".ini", ".sh", ".bash",
    ".service", ".tpl", ".env",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
