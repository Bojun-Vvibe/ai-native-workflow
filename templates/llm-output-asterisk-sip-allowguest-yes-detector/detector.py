#!/usr/bin/env python3
"""Detect Asterisk SIP / chan_sip / pjsip configurations that leave
``allowguest = yes`` (or its pjsip equivalent ``anonymous`` endpoint
with ``identify`` matching ``0.0.0.0/0``) on a publicly reachable
``[general]`` block.

When ``allowguest = yes`` is set in ``sip.conf [general]`` (the
chan_sip default historically was ``yes``), Asterisk will accept
INVITEs from peers it has no credentials for and route them
according to the dialplan's ``[default]`` context (or any context
named in the request URI). Combined with a permissive dialplan
this is the canonical "phone bill in the morning" misconfiguration:
attackers place toll-fraud calls to premium-rate numbers via
PSTN trunks, with no authentication.

For pjsip, the equivalent shape is an endpoint named ``anonymous``
(or with no auth) used by an ``identify`` section that does not
restrict ``match`` to a known peer subnet -- callers are matched
to the anonymous endpoint and routed by context.

What's flagged
--------------
Per file (line-level):

* ``allowguest = yes`` / ``allowguest=yes`` / ``allowguest=true``
  in any ``[section]`` (chan_sip).
* ``allowguest = 1`` (chan_sip alt form).
* ``alwaysauthreject = no`` (lets attackers enumerate extensions
  by username).
* ``autocreatepeer = yes`` (chan_sip; auto-creates peers from
  arbitrary INVITEs).
* ``insecure = invite,port`` and similar permissive variants on a
  ``type=peer`` / ``type=friend`` entry.
* In pjsip configs (``pjsip.conf``-shape): an endpoint section
  whose ``type`` is ``endpoint`` and whose ``auth`` setting is
  empty or omitted, paired with an ``identify`` section whose
  ``match`` is ``0.0.0.0/0`` / ``::/0`` / ``any``.

Per file (whole-file):

* The file is a ``sip.conf``-shape (has a ``[general]`` block AND
  references ``context=`` or ``allowguest`` or ``bindport``) AND
  ``allowguest`` is unset (chan_sip historic default was ``yes``).

What's NOT flagged
------------------
* ``allowguest = no``.
* ``insecure = invite`` on a ``type=peer`` whose ``host = dynamic``
  AND ``deny = 0.0.0.0/0`` AND ``permit = <specific subnet>``.
* Lines with a trailing ``# sip-guest-ok`` comment.
* Files containing ``# sip-guest-ok-file`` anywhere.
* Blocks bracketed by ``# sip-guest-ok-begin`` /
  ``# sip-guest-ok-end``.

Refs
----
* CWE-284: Improper Access Control
* CWE-306: Missing Authentication for Critical Function
* CWE-1188: Insecure Default Initialization of Resource
* Asterisk security advisory AST-2009-003 (allowguest / toll fraud)

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Dict, Iterable, List, Tuple

# Markers may use either ';' (Asterisk) or '#' as comment leader.
OK_LINE = "sip-guest-ok"
OK_FILE = "sip-guest-ok-file"
OK_BEGIN = "sip-guest-ok-begin"
OK_END = "sip-guest-ok-end"

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.+?)\s*$")

ALLOWGUEST_TRUE = {"yes", "true", "1", "on"}
ALLOWGUEST_FALSE = {"no", "false", "0", "off"}

ANY_MATCH = {"0.0.0.0/0", "::/0", "any", "0.0.0.0", "::"}


def _looks_like_chan_sip(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if base in {"sip.conf", "sip_general_custom.conf", "sip_custom.conf"}:
        return True
    return ("[general]" in text) and re.search(
        r"^\s*(?:allowguest|bindport|context|alwaysauthreject)\s*=",
        text,
        re.MULTILINE,
    ) is not None


def _looks_like_pjsip(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if base in {"pjsip.conf", "pjsip_custom.conf"}:
        return True
    return re.search(r"^\s*type\s*=\s*(?:endpoint|identify|aor|auth)\s*$",
                     text, re.MULTILINE) is not None


def _strip_inline_comment(line: str) -> Tuple[str, bool]:
    """Return (stripped_line, has_ok_marker)."""
    has_ok = OK_LINE in line
    # Asterisk uses ; for inline comments.
    out = line.split(";", 1)[0]
    return out, has_ok


def _walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    yield os.path.join(root, f)
        else:
            yield p


def _scan_chan_sip(path: str, text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []

    # Pass 1: build a complete map of sections -> kv pairs (across the whole file).
    full_sections: Dict[str, Dict[str, str]] = {}
    cur = None
    skip = False
    for raw in lines:
        if OK_BEGIN in raw:
            skip = True
            continue
        if OK_END in raw:
            skip = False
            continue
        if skip:
            continue
        m_sec = SECTION_RE.match(raw)
        if m_sec:
            cur = m_sec.group(1).strip().lower()
            full_sections.setdefault(cur, {})
            continue
        body, _ = _strip_inline_comment(raw)
        m_kv = KV_RE.match(body)
        if m_kv and cur is not None:
            full_sections[cur][m_kv.group(1).lower()] = m_kv.group(2).strip()

    # Pass 2: emit findings.
    section = None
    skip = False
    saw_allowguest = False
    for i, raw in enumerate(lines, 1):
        if OK_BEGIN in raw:
            skip = True
            continue
        if OK_END in raw:
            skip = False
            continue
        if skip:
            continue

        m_sec = SECTION_RE.match(raw)
        if m_sec:
            section = m_sec.group(1).strip().lower()
            continue

        body, has_ok = _strip_inline_comment(raw)
        m_kv = KV_RE.match(body)
        if not m_kv:
            continue
        key = m_kv.group(1).lower()
        val = m_kv.group(2).strip().lower()

        if key == "allowguest":
            saw_allowguest = True
            if val in ALLOWGUEST_TRUE and not has_ok:
                findings.append((i, f"allowguest={val} permits unauthenticated SIP INVITEs"))
        elif key == "alwaysauthreject":
            if val in {"no", "false", "0", "off"} and not has_ok:
                findings.append(
                    (i, "alwaysauthreject=no leaks valid extensions on auth failure")
                )
        elif key == "autocreatepeer":
            if val in ALLOWGUEST_TRUE and not has_ok:
                findings.append(
                    (i, f"autocreatepeer={val} auto-trusts arbitrary SIP peers")
                )
        elif key == "insecure":
            tokens = {t.strip() for t in val.split(",")}
            if "invite" in tokens and not has_ok:
                sec = full_sections.get(section, {})
                deny_all = sec.get("deny", "") == "0.0.0.0/0"
                permit_val = sec.get("permit", "")
                permit_specific = bool(permit_val) and permit_val not in (
                    "0.0.0.0/0",
                    "::/0",
                    "any",
                )
                if not (deny_all and permit_specific):
                    findings.append(
                        (i, f"insecure={val} on SIP peer disables INVITE authentication")
                    )

    if not saw_allowguest and "general" in full_sections and OK_FILE not in text:
        gen_line = 1
        for i, raw in enumerate(lines, 1):
            m = SECTION_RE.match(raw)
            if m and m.group(1).strip().lower() == "general":
                gen_line = i
                break
        findings.append(
            (gen_line, "sip.conf [general] has no explicit allowguest -- chan_sip default is yes")
        )

    return findings


def _scan_pjsip(path: str, text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    sections: Dict[str, Dict[str, Tuple[int, str]]] = {}
    section_order: List[str] = []
    section = None
    skip = False

    for i, raw in enumerate(lines, 1):
        if OK_BEGIN in raw:
            skip = True
            continue
        if OK_END in raw:
            skip = False
            continue
        if skip:
            continue
        m_sec = SECTION_RE.match(raw)
        if m_sec:
            section = m_sec.group(1).strip()
            sections[section] = {"_line": (i, "")}
            section_order.append(section)
            continue
        body, _ = _strip_inline_comment(raw)
        m_kv = KV_RE.match(body)
        if not m_kv or section is None:
            continue
        sections[section][m_kv.group(1).lower()] = (i, m_kv.group(2).strip())

    # Look for endpoint sections lacking auth, paired with permissive identify match.
    permissive_identify_matches = set()
    for name, props in sections.items():
        if props.get("type", (0, ""))[1] == "identify":
            match = props.get("match", (0, ""))[1].strip().lower()
            endpoint = props.get("endpoint", (0, ""))[1].strip()
            if match in ANY_MATCH:
                permissive_identify_matches.add(endpoint)

    for name, props in sections.items():
        if props.get("type", (0, ""))[1] != "endpoint":
            continue
        auth = props.get("auth", (0, ""))[1].strip()
        line_no = props["_line"][0]
        if not auth:
            # only flag if some identify matches it from anywhere
            if name in permissive_identify_matches or name.lower() == "anonymous":
                findings.append(
                    (line_no,
                     f"pjsip endpoint [{name}] has no auth and is reachable from anywhere")
                )

    return findings


def _scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    if OK_FILE in text:
        return []
    lines = text.splitlines()

    findings: List[Tuple[int, str]] = []
    if _looks_like_chan_sip(path, text):
        findings.extend(_scan_chan_sip(path, text, lines))
    if _looks_like_pjsip(path, text):
        findings.extend(_scan_pjsip(path, text, lines))
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    flagged_files = 0
    for path in _walk(argv[1:]):
        if path.endswith((".png", ".jpg", ".gz", ".tar", ".zip")):
            continue
        findings = _scan_file(path)
        if findings:
            flagged_files += 1
            for ln, reason in findings:
                print(f"{path}:{ln}:{reason}")
    return min(flagged_files, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
