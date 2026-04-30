#!/usr/bin/env python3
"""Detect XML parsing calls vulnerable to XML External Entity (XXE) attacks.

Python's stdlib `xml.etree.ElementTree`, `xml.dom.minidom`,
`xml.dom.pulldom`, `xml.sax`, and `xml.parsers.expat` all process
external entities by default in older runtimes and various
third-party parsers (notably `lxml.etree.parse` without
`resolve_entities=False` / a hardened `XMLParser`). An attacker
who can supply XML can read local files, exhaust memory via
billion-laughs, or pivot to SSRF.

The hardened path is `defusedxml` (`defusedxml.ElementTree.parse`,
`defusedxml.lxml.parse`, etc.) or `lxml.etree.XMLParser(
resolve_entities=False, no_network=True, dtd_validation=False)`
explicitly passed to the parse call.

LLMs love to emit `ET.parse(user_supplied_path)` because that's
the canonical "parse XML in Python" snippet. This detector flags
the unsafe surfaces.

What this flags
---------------
* `xml.etree.ElementTree.parse(...)`, `.fromstring(...)`,
  `.iterparse(...)`, `.XML(...)`, `.XMLParser(...)`
* Same calls via the common `ET` / `etree` aliases
* `xml.dom.minidom.parse(...)` / `.parseString(...)`
* `xml.dom.pulldom.parse(...)` / `.parseString(...)`
* `xml.sax.parse(...)` / `.parseString(...)` /
  `.make_parser(...)`
* `xml.parsers.expat.ParserCreate(...)`
* `lxml.etree.parse(...)` / `.fromstring(...)` /
  `.XML(...)` / `.iterparse(...)` *unless* a hardened
  `XMLParser(resolve_entities=False, ...)` argument is visible
  on the same line

What this does NOT flag
-----------------------
* Anything in the `defusedxml.*` namespace
* Lines marked with a trailing `# xxe-ok` comment
* Occurrences inside `#` comments or string literals

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python shebang
files).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Always-unsafe stdlib XML surfaces.
RE_STDLIB = re.compile(
    r"\b(?:"
    r"xml\s*\.\s*etree\s*\.\s*ElementTree\s*\.\s*(?:parse|fromstring|iterparse|XML|XMLParser)"
    r"|xml\s*\.\s*dom\s*\.\s*minidom\s*\.\s*(?:parse|parseString)"
    r"|xml\s*\.\s*dom\s*\.\s*pulldom\s*\.\s*(?:parse|parseString)"
    r"|xml\s*\.\s*sax\s*\.\s*(?:parse|parseString|make_parser)"
    r"|xml\s*\.\s*parsers\s*\.\s*expat\s*\.\s*ParserCreate"
    r")\s*\("
)

# Aliased ET / etree imports — `ET.parse(...)`, `etree.parse(...)`.
# Flag only when the alias clearly comes from xml.etree.ElementTree
# context. We approximate by flagging on `ET.` / `etree.` (and
# `minidom.`, `pulldom.`) prefixes — the false-positive risk is
# low because these names are conventional for XML libs.
RE_ALIAS = re.compile(
    r"\b(?:ET|etree|minidom|pulldom)\s*\.\s*(parse|fromstring|iterparse|XML|parseString)\s*\("
)

# lxml — separately handled because there's a safe escape hatch.
RE_LXML = re.compile(
    r"\blxml\s*\.\s*etree\s*\.\s*(parse|fromstring|iterparse|XML)\s*\("
)

RE_HARDENED_LXML = re.compile(
    r"resolve_entities\s*=\s*False"
)

RE_DEFUSED = re.compile(r"\bdefusedxml\b")
RE_SUPPRESS = re.compile(r"#\s*xxe-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Blank Python comment tails and string literal contents,
    preserving column positions and quote tokens.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


# Imports that bind XML aliases to the safe defusedxml namespace.
# Examples:
#   import defusedxml.ElementTree as ET
#   import defusedxml.minidom as minidom
#   from defusedxml import ElementTree as ET
#   import defusedxml.lxml
RE_DEFUSED_IMPORT_AS = re.compile(
    r"^\s*(?:from\s+defusedxml(?:\s*\.[A-Za-z_][\w.]*)?\s+import\s+\S+\s+as\s+(\w+)"
    r"|import\s+defusedxml\s*\.\s*[A-Za-z_]\w*\s+as\s+(\w+))"
)
RE_DEFUSED_IMPORT_PLAIN = re.compile(
    r"^\s*(?:from\s+defusedxml(?:\s*\.[A-Za-z_][\w.]*)?\s+import\s+([\w,\s]+)"
    r"|import\s+defusedxml\s*\.\s*([A-Za-z_]\w*))"
)

# When a hardened lxml.etree.XMLParser is built in this file we
# treat downstream lxml.etree.parse(...) calls as safe — the
# common idiom is `parser = XMLParser(resolve_entities=False); ...
# lxml.etree.parse(path, parser)`.
RE_HARDENED_PARSER_DECL = re.compile(
    r"\bXMLParser\s*\([^)]*resolve_entities\s*=\s*False"
)


def collect_safe_aliases(text: str) -> set[str]:
    safe: set[str] = set()
    for raw in text.splitlines():
        m = RE_DEFUSED_IMPORT_AS.match(raw)
        if m:
            alias = m.group(1) or m.group(2)
            if alias:
                safe.add(alias)
            continue
        m = RE_DEFUSED_IMPORT_PLAIN.match(raw)
        if m:
            block = m.group(1) or m.group(2) or ""
            for name in re.split(r"[,\s]+", block.strip()):
                if name:
                    safe.add(name)
    return safe


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    safe_aliases = collect_safe_aliases(text)
    file_has_hardened_parser = bool(RE_HARDENED_PARSER_DECL.search(text))
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue
        # Lines that mention defusedxml directly are safe wrappers.
        if RE_DEFUSED.search(scrub):
            continue
        for m in RE_STDLIB.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "xxe-stdlib-xml-parse", raw.strip())
            )
        for m in RE_ALIAS.finditer(scrub):
            # Skip if this is actually a `lxml.etree.<...>` call —
            # those are handled by RE_LXML below with hardening
            # detection.
            preceding = scrub[max(0, m.start() - 8):m.start()]
            if re.search(r"\blxml\s*\.\s*$", preceding):
                continue
            # Figure out the alias prefix (text before `.<method>(`)
            prefix_match = re.search(
                r"\b(\w+)\s*\.\s*" + re.escape(m.group(1)) + r"\s*\(",
                scrub[max(0, m.start() - 32):m.end()],
            )
            alias = prefix_match.group(1) if prefix_match else ""
            if alias in safe_aliases:
                continue
            findings.append(
                (path, idx, m.start() + 1,
                 f"xxe-alias-{m.group(1).lower()}", raw.strip())
            )
        for m in RE_LXML.finditer(scrub):
            if RE_HARDENED_LXML.search(scrub) or file_has_hardened_parser:
                continue
            findings.append(
                (path, idx, m.start() + 1,
                 f"xxe-lxml-{m.group(1).lower()}-no-hardening", raw.strip())
            )
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
