#!/usr/bin/env python3
"""Detect unsafe ``yaml.load`` usage in LLM-emitted Python.

PyYAML's ``yaml.load`` defaults (prior to 5.1) and any explicit use of
``Loader=yaml.Loader`` / ``yaml.UnsafeLoader`` / ``yaml.FullLoader`` allow
construction of arbitrary Python objects from a YAML stream. A YAML
document such as::

    !!python/object/apply:os.system ["rm -rf /"]

deserialises into a side-effecting call. This is a textbook arbitrary
code execution sink whenever the YAML input is attacker-influenced
(config from disk, network payload, user upload, ...).

LLMs emit ``yaml.load(stream)`` by reflex because:

1. It is the shortest "load YAML" snippet and matches the older
   PyYAML tutorials (pre-2019).
2. Many Stack Overflow answers still show ``yaml.load(open(...))``
   without a Loader argument.
3. ``safe_load`` requires the model to know the safe-API exists.

CWE references
--------------
* **CWE-502**: Deserialization of Untrusted Data.
* **CWE-94**:  Improper Control of Generation of Code ('Code Injection').
* **CWE-20**:  Improper Input Validation.

What this flags
---------------
* ``yaml.load(stream)``                       — no Loader, pre-5.1 default unsafe.
* ``yaml.load(stream, Loader=yaml.Loader)``   — explicit unsafe Loader.
* ``yaml.load(stream, Loader=yaml.UnsafeLoader)``
* ``yaml.load(stream, Loader=yaml.FullLoader)`` — FullLoader still
  permits ``!!python/object/new`` constructors that can call arbitrary
  classes; CVE-2020-14343 documented this. Bandit B506 also flags it.
* ``yaml.load_all(stream[, Loader=...])``    — same risk, multi-doc.
* ``yaml.unsafe_load(stream)``               — explicitly unsafe API.
* ``yaml.unsafe_load_all(stream)``

What this does NOT flag
-----------------------
* ``yaml.safe_load(...)`` / ``yaml.safe_load_all(...)``.
* ``yaml.load(stream, Loader=yaml.SafeLoader)`` /
  ``yaml.load(stream, Loader=yaml.CSafeLoader)``.
* ``yaml.load`` mentioned inside a ``#`` comment or a string literal.
* Lines suffixed with the suppression marker ``# yaml-unsafe-ok``
  (e.g. for trusted in-process round-trip of internally generated data).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# yaml-unsafe-ok"

# yaml.load( ... )  or  yaml.load_all( ... )
RE_YAML_LOAD_CALL = re.compile(r"\byaml\s*\.\s*load(?:_all)?\s*\(")

# yaml.unsafe_load( ... ) / yaml.unsafe_load_all( ... )
RE_YAML_UNSAFE_LOAD = re.compile(r"\byaml\s*\.\s*unsafe_load(?:_all)?\s*\(")

# Loader=yaml.SafeLoader / Loader=SafeLoader / Loader=yaml.CSafeLoader
RE_SAFE_LOADER_KWARG = re.compile(
    r"Loader\s*=\s*(?:yaml\s*\.\s*)?(?:C?SafeLoader)\b"
)

# Loader=yaml.Loader / FullLoader / UnsafeLoader / CLoader / CFullLoader / CUnsafeLoader
RE_UNSAFE_LOADER_KWARG = re.compile(
    r"Loader\s*=\s*(?:yaml\s*\.\s*)?C?(?:Loader|FullLoader|UnsafeLoader)\b"
)


def _strip_comment_and_strings(line: str) -> str:
    """Replace string-literal contents with spaces, drop ``#`` comments."""
    out: list[str] = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_comment_and_strings(raw)
        if "yaml" not in line:
            continue

        # yaml.unsafe_load[_all]( -- always a finding.
        if RE_YAML_UNSAFE_LOAD.search(line):
            findings.append((path, lineno, "yaml-unsafe-load-api", raw.rstrip()))
            continue

        if RE_YAML_LOAD_CALL.search(line):
            # If a SafeLoader kwarg is on the same line, it is fine.
            if RE_SAFE_LOADER_KWARG.search(line):
                continue
            if RE_UNSAFE_LOADER_KWARG.search(line):
                findings.append(
                    (path, lineno, "yaml-load-unsafe-loader", raw.rstrip())
                )
                continue
            # No Loader= kwarg at all on this line → pre-5.1 default
            # behaviour or relying on unsafe default. Flag.
            if "Loader=" not in line:
                findings.append(
                    (path, lineno, "yaml-load-no-loader", raw.rstrip())
                )
                continue
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.py")):
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
