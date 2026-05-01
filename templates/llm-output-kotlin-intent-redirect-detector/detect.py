#!/usr/bin/env python3
"""Detect intent-redirect / unvalidated-intent-launch in LLM-emitted Kotlin.

Android's ``Intent`` system is a frequent confused-deputy surface. A
component that receives an ``Intent`` from another app (via an exported
Activity, Service, BroadcastReceiver, or PendingIntent), extracts a
nested intent or component name from its extras, and then immediately
launches it, lets the caller redirect the privileged component into
arbitrary internal Activities — bypassing exported=false, leaking
permission-protected screens, or pivoting through ``setResult``.

This is CWE-927 (use of implicit intent for sensitive communication)
and the "Intent Redirection" class documented in Google Play's App
Security Improvement Program.

What this flags
---------------
A line in a ``.kt`` file that pulls a nested intent / component out of
incoming extras and then launches it, when the same file never gates
the launch through any of the recognised mitigations (resolved
component check, package allowlist, explicit ``setPackage`` /
``setClassName`` / ``setComponent`` of a *known* class, or the modern
``PendingIntent.FLAG_IMMUTABLE``)::

    val next = intent.getParcelableExtra<Intent>("next")
    startActivity(next)

    val name = intent.getStringExtra("target")
    val redirect = Intent().apply { setClassName(packageName, name) }
    startActivity(redirect)

What this does NOT flag
-----------------------
* Files where any mitigation token appears anywhere.
* Lines suffixed with ``// intent-ok``.
* Construction inside string literals or after ``//`` line comments.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// intent-ok"

# Risky extraction: pulling a nested Intent / ComponentName / class
# name string out of incoming extras.
RE_RISKY_EXTRACT = re.compile(
    r"\b(?:intent|getIntent\(\)|incoming|extras)\s*\.\s*("
    r"getParcelableExtra|"
    r"getParcelable|"
    r"getStringExtra|"
    r"getBundleExtra|"
    r"getSerializableExtra"
    r")\s*(?:<[^>]+>)?\s*\("
)

# Risky launch surface: starting an Activity / Service / Broadcast
# *with a variable*, or constructing a PendingIntent from one.
RE_RISKY_LAUNCH = re.compile(
    r"\b("
    r"startActivity|"
    r"startActivityForResult|"
    r"startActivities|"
    r"startService|"
    r"startForegroundService|"
    r"bindService|"
    r"sendBroadcast|"
    r"sendOrderedBroadcast|"
    r"PendingIntent\s*\.\s*getActivity|"
    r"PendingIntent\s*\.\s*getBroadcast|"
    r"PendingIntent\s*\.\s*getService"
    r")\s*\("
)

# Mitigations — any of these tokens anywhere in the file silences findings.
RE_MITIGATIONS = re.compile(
    r"(?:"
    r"resolveActivity\s*\(|"
    r"resolveActivityInfo\s*\(|"
    r"queryIntentActivities\s*\(|"
    r"FLAG_IMMUTABLE|"
    r"setPackage\s*\(\s*\"[A-Za-z0-9_.]+\"\s*\)|"
    r"setClassName\s*\(\s*\"[A-Za-z0-9_.]+\"\s*,\s*\"[A-Za-z0-9_.$]+\"\s*\)|"
    r"ComponentName\s*\(\s*\"[A-Za-z0-9_.]+\"\s*,\s*\"[A-Za-z0-9_.$]+\"\s*\)|"
    r"INTENT_REDIRECT_ALLOWLIST|"
    r"validateRedirectTarget"
    r")"
)


def _strip_strings_and_comments(line: str, in_triple: bool) -> tuple[str, bool]:
    # Kotlin-aware: handle "..." and triple-quoted raw strings and // comments.
    # `in_triple` carries triple-quote state across lines.
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False  # regular "..."
    in_t = in_triple
    while i < n:
        ch = line[i]
        if in_t:
            if ch == '"' and i + 2 < n and line[i + 1] == '"' and line[i + 2] == '"':
                in_t = False
                out.append('"""')
                i += 3
                continue
            out.append(" ")
        elif in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
                out.append('"')
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == '"' and i + 2 < n and line[i + 1] == '"' and line[i + 2] == '"':
                in_t = True
                out.append('"""')
                i += 3
                continue
            if ch == '"':
                in_s = True
                out.append('"')
            else:
                out.append(ch)
        i += 1
    return "".join(out), in_t


def _file_has_mitigations(text: str) -> bool:
    return RE_MITIGATIONS.search(text) is not None


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    if _file_has_mitigations(text):
        return findings
    # File must both extract from incoming intent extras AND launch
    # something — otherwise it's not a redirect surface.
    has_extract = False
    extract_lines: list[tuple[int, str, str]] = []
    launch_lines: list[tuple[int, str, str]] = []
    in_triple = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped, in_triple = _strip_strings_and_comments(raw, in_triple)
        if SUPPRESS in raw:
            continue
        m = RE_RISKY_EXTRACT.search(stripped)
        if m:
            has_extract = True
            extract_lines.append((lineno, f"intent-redirect-extract-{m.group(1)}", raw.rstrip()))
        m2 = RE_RISKY_LAUNCH.search(stripped)
        if m2:
            kind = m2.group(1).replace(" ", "").replace(".", "-")
            launch_lines.append((lineno, f"intent-redirect-launch-{kind}", raw.rstrip()))
    if has_extract and launch_lines:
        for lineno, kind, line in extract_lines:
            findings.append((path, lineno, kind, line))
        for lineno, kind, line in launch_lines:
            findings.append((path, lineno, kind, line))
    findings.sort(key=lambda t: t[1])
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.kt")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
