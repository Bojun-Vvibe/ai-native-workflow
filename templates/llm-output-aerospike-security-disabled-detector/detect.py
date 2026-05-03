#!/usr/bin/env python3
"""
llm-output-aerospike-security-disabled-detector

Flags Aerospike configurations / invocations that explicitly
disable the security subsystem, leaving the cluster open to
anonymous administrative access on the service port (default 3000).

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-732: Incorrect Permission Assignment for Critical Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Dockerfile, docker-compose.*, *.yaml, *.yml, *.sh, *.bash, *.service,
*.env, *.tpl, *.conf).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# enable-security false  (any whitespace, optional = or :)
_ENABLE_SECURITY_FALSE = re.compile(
    r"""enable-security\s*[:=]?\s*['"]?(false|0|no|off)['"]?\b""",
    re.IGNORECASE,
)
_ENABLE_SECURITY_TRUE = re.compile(
    r"""enable-security\s*[:=]?\s*['"]?(true|1|yes|on)['"]?\b""",
    re.IGNORECASE,
)
_ENABLE_SECURITY_KEY = re.compile(
    r"""\benable-security\b""",
    re.IGNORECASE,
)

# Env override: SECURITY_ENABLED=false / =0 / =no / =off
_ENV_SECURITY_DISABLED = re.compile(
    r"""(?im)^\s*(?:export\s+|-\s+|Environment=)?SECURITY_ENABLED\s*[:=]\s*['"]?(false|0|no|off)['"]?\b"""
)

# k8s/compose env list pair: name: SECURITY_ENABLED on this line,
# value on the next non-blank line.
_ENV_LIST_NAME = re.compile(r"""(?i)\bSECURITY_ENABLED\b""")

_COMMENT_LINE = re.compile(r"""^\s*(?:#|//)""")

_AEROSPIKE_CTX = re.compile(
    r"""(?i)\baerospike\b|image:\s*['"]?aerospike"""
)


def _strip_inline_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/" \
                and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _aerospike_context(text: str) -> bool:
    return bool(_AEROSPIKE_CTX.search(text))


def _find_security_stanzas(lines: List[str]) -> List[tuple]:
    """Return list of (open_lineno, close_lineno) for security {} blocks.

    Brace tracking is approximate — Aerospike configs use a Tcl-ish
    syntax with `name { ... }` blocks. We scan for `security {` and
    pair it with the matching `}` at the same depth.
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _COMMENT_LINE.match(line):
            i += 1
            continue
        m = re.search(r"""(?i)^\s*security\s*\{""", line)
        if m:
            depth = line.count("{") - line.count("}")
            start = i
            j = i + 1
            while j < len(lines) and depth > 0:
                lj = lines[j]
                if not _COMMENT_LINE.match(lj):
                    depth += lj.count("{") - lj.count("}")
                j += 1
            out.append((start + 1, j))
        i += 1
    return out


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_aero_file = _aerospike_context(text)
    lines = text.splitlines()

    # --- Env override (any file)
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)
        if _ENV_SECURITY_DISABLED.search(line):
            findings.append(
                f"{path}:{lineno}: SECURITY_ENABLED=false env "
                f"override disables Aerospike security; cluster "
                f"accepts anonymous administrative connections "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )

    # --- k8s/compose env list pair: name: SECURITY_ENABLED + value: false
    if in_aero_file:
        for lineno, raw in enumerate(lines, start=1):
            if _COMMENT_LINE.match(raw):
                continue
            line = _strip_inline_comment(raw)
            if _ENV_LIST_NAME.search(line) and "=" not in line \
                    and ":" in line:
                for j in range(lineno, min(lineno + 3, len(lines))):
                    nxt = lines[j]
                    vm = re.search(
                        r"""(?i)\bvalue\s*:\s*['"]?(false|0|no|off)['"]?""",
                        nxt,
                    )
                    if vm:
                        findings.append(
                            f"{path}:{lineno}: SECURITY_ENABLED env "
                            f"(k8s list form) set to {vm.group(1)!r} "
                            f"disables Aerospike security "
                            f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
                        )
                        break

    # --- aerospike.conf: security { ... } stanzas
    if in_aero_file:
        stanzas = _find_security_stanzas(lines)
        for open_ln, close_ln in stanzas:
            stanza_lines = lines[open_ln - 1:close_ln]
            stanza_text = "\n".join(stanza_lines)
            # collect non-blank, non-comment, non-brace lines
            body = []
            for sl in stanza_lines[1:-1]:
                if not sl.strip():
                    continue
                if _COMMENT_LINE.match(sl):
                    continue
                if sl.strip() in {"{", "}"}:
                    continue
                body.append(sl)
            has_false = bool(_ENABLE_SECURITY_FALSE.search(stanza_text))
            has_true = bool(_ENABLE_SECURITY_TRUE.search(stanza_text))
            has_key = bool(_ENABLE_SECURITY_KEY.search(stanza_text))

            if has_false:
                # find the actual line number of the false directive
                for k, sl in enumerate(stanza_lines):
                    if _COMMENT_LINE.match(sl):
                        continue
                    if _ENABLE_SECURITY_FALSE.search(
                        _strip_inline_comment(sl)
                    ):
                        findings.append(
                            f"{path}:{open_ln + k}: aerospike.conf "
                            f"security {{}} stanza sets "
                            f"enable-security false; cluster "
                            f"accepts anonymous administrative "
                            f"connections (CWE-306/CWE-1188): "
                            f"{sl.strip()[:160]}"
                        )
                        break
            elif body and not has_key and not has_true:
                # non-empty stanza with no enable-security key set ->
                # default is false per Aerospike reference.
                findings.append(
                    f"{path}:{open_ln}: aerospike.conf security {{}} "
                    f"stanza omits enable-security; default is "
                    f"'false' so the cluster runs unauthenticated "
                    f"(CWE-1188/CWE-306): "
                    f"{stanza_lines[0].strip()[:160]}"
                )

    # --- Top-level legacy `enable-security false` (no stanza)
    if in_aero_file:
        # build a set of line ranges already inside a stanza
        stanza_ranges = _find_security_stanzas(lines)
        in_stanza = set()
        for o, c in stanza_ranges:
            for k in range(o, c + 1):
                in_stanza.add(k)
        for lineno, raw in enumerate(lines, start=1):
            if lineno in in_stanza:
                continue
            if _COMMENT_LINE.match(raw):
                continue
            line = _strip_inline_comment(raw)
            if _ENABLE_SECURITY_FALSE.search(line):
                findings.append(
                    f"{path}:{lineno}: top-level legacy "
                    f"`enable-security false` disables Aerospike "
                    f"auth (CWE-306/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "aerospike.conf",
    "aerospike.template.conf",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tpl", ".env",
    ".conf",
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
