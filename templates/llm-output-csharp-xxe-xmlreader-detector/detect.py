#!/usr/bin/env python3
"""Detect XXE-prone XML reader construction in LLM-emitted C#.

LLMs writing C# / .NET frequently emit::

    var doc = new XmlDocument();
    doc.Load(input);

    var reader = XmlReader.Create(input);

    var ser = new XmlSerializer(typeof(T));
    ser.Deserialize(reader);

…without first locking down DTD / external-entity resolution. Behaviour
varies by .NET runtime version: legacy ``XmlDocument`` / ``XmlTextReader``
default to processing DTDs, ``XmlReader.Create`` honours the
``XmlReaderSettings.DtdProcessing`` you (don't) pass in, and
``XPathDocument`` will resolve external entities through any non-null
``XmlResolver``. The resulting hazards are the standard XXE set:
local-file disclosure, SSRF, billion-laughs DoS, OOB exfiltration.

What this flags
---------------
A line in a ``.cs`` file that constructs an at-risk XML reader and the
*same file* never opts in to any of the recognised mitigations::

    settings.DtdProcessing = DtdProcessing.Prohibit;
    settings.DtdProcessing = DtdProcessing.Ignore;
    settings.XmlResolver = null;
    doc.XmlResolver = null;
    reader.XmlResolver = null;

What this does NOT flag
-----------------------
* Files where any mitigation token appears anywhere.
* Lines suffixed with ``// xxe-ok``.
* Constructions inside string literals or single-line ``//`` comments.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// xxe-ok"

RE_RISKY_NEW = re.compile(
    r"\bnew\s+("
    r"XmlDocument|"
    r"XmlTextReader|"
    r"XPathDocument|"
    r"XmlSerializer|"
    r"DataSet|"
    r"DataTable"
    r")\s*\("
)
RE_RISKY_CREATE = re.compile(
    r"\b(XmlReader|XmlDictionaryReader)\s*\.\s*Create\s*\("
)
RE_RISKY_LOAD = re.compile(
    r"\b(XmlDocument|XPathDocument|XDocument|XElement)\s*\.\s*Load\s*\("
)

RE_MITIGATIONS = re.compile(
    r"(?:"
    r"DtdProcessing\s*\.\s*(?:Prohibit|Ignore)|"
    r"XmlResolver\s*=\s*null|"
    r"ProhibitDtd\s*=\s*true|"
    r"MaxCharactersFromEntities\s*=|"
    r"XmlSecureResolver|"
    r"new\s+XmlReaderSettings\s*\([^)]*\)\s*\{[^}]*DtdProcessing"
    r")"
)


def _strip_strings_and_comments(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_v = False  # @"..." verbatim string (no escapes)
    in_c = False  # 'x' char literal
    while i < n:
        ch = line[i]
        if in_v:
            if ch == '"':
                # check doubled "" → literal "
                if i + 1 < n and line[i + 1] == '"':
                    out.append("  ")
                    i += 2
                    continue
                in_v = False
                out.append('"')
            else:
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
        elif in_c:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_c = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == "@" and i + 1 < n and line[i + 1] == '"':
                in_v = True
                out.append(' "')
                i += 2
                continue
            if ch == '"':
                in_s = True
                out.append('"')
            elif ch == "'":
                in_c = True
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


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
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        stripped = _strip_strings_and_comments(raw)
        m = RE_RISKY_NEW.search(stripped)
        if m:
            findings.append((path, lineno, f"xxe-new-{m.group(1)}", raw.rstrip()))
            continue
        m2 = RE_RISKY_CREATE.search(stripped)
        if m2:
            findings.append((path, lineno, f"xxe-{m2.group(1)}-Create", raw.rstrip()))
            continue
        m3 = RE_RISKY_LOAD.search(stripped)
        if m3:
            findings.append((path, lineno, f"xxe-{m3.group(1)}-Load", raw.rstrip()))
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.cs")):
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
