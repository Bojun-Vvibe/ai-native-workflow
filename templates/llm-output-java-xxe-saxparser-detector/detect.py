#!/usr/bin/env python3
"""Detect XXE-prone XML parser construction in LLM-emitted Java.

LLMs emitting Java commonly write::

    SAXParserFactory f = SAXParserFactory.newInstance();
    DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
    XMLInputFactory xif = XMLInputFactory.newInstance();
    TransformerFactory tf = TransformerFactory.newInstance();
    SchemaFactory sf = SchemaFactory.newInstance(...);

…and then immediately parse untrusted XML, without first disabling
external entity / DOCTYPE resolution. The default JDK configuration
resolves DOCTYPEs and external general / parameter entities, which
permits classic XXE: file disclosure, SSRF, billion-laughs DoS, and
out-of-band data exfiltration.

What this flags
---------------
A line that constructs one of the at-risk factories via ``newInstance``
or instantiates ``new SAXParser()`` / ``new SAXBuilder()`` (JDOM) /
``new SAXReader()`` (dom4j), when the *same file* never sets any of the
mitigating features / properties anywhere::

    f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
    f.setFeature("http://xml.org/sax/features/external-general-entities", false)
    f.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
    dbf.setExpandEntityReferences(false)
    dbf.setXIncludeAware(false)
    xif.setProperty(XMLInputFactory.SUPPORT_DTD, false)
    xif.setProperty("javax.xml.stream.isSupportingExternalEntities", false)
    tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
    tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "")
    sf.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "")
    sf.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")
    saxBuilder.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
    saxReader.setFeature(...)

What this does NOT flag
-----------------------
* Files where any mitigating feature/property/attribute is configured
  somewhere in the file. (Coarse but matches the common LLM mistake of
  never disabling DOCTYPEs at all.)
* Lines suffixed with ``// xxe-ok``.
* Constructions inside string literals or single-line ``//`` comments.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// xxe-ok"

# Risky factory constructions. We require the class name + .newInstance(
# or specific `new <Builder>()` instantiations.
RE_RISKY_NEWINSTANCE = re.compile(
    r"\b("
    r"SAXParserFactory|"
    r"DocumentBuilderFactory|"
    r"XMLInputFactory|"
    r"TransformerFactory|"
    r"SchemaFactory|"
    r"XMLReaderFactory|"
    r"SAXTransformerFactory"
    r")\s*\.\s*newInstance\s*\("
)
RE_RISKY_NEW_BUILDER = re.compile(
    r"\bnew\s+("
    r"SAXBuilder|"
    r"SAXReader"
    r")\s*\("
)

# Mitigation indicators — if ANY of these appear in the same file we
# treat it as "the author at least knew about XXE" and stay silent.
RE_MITIGATIONS = re.compile(
    r"(?:"
    r"disallow-doctype-decl|"
    r"external-general-entities|"
    r"external-parameter-entities|"
    r"load-external-dtd|"
    r"setExpandEntityReferences\s*\(\s*false\s*\)|"
    r"setXIncludeAware\s*\(\s*false\s*\)|"
    r"XMLConstants\.FEATURE_SECURE_PROCESSING|"
    r"XMLConstants\.ACCESS_EXTERNAL_DTD|"
    r"XMLConstants\.ACCESS_EXTERNAL_SCHEMA|"
    r"XMLConstants\.ACCESS_EXTERNAL_STYLESHEET|"
    r"XMLInputFactory\s*\.\s*SUPPORT_DTD|"
    r"isSupportingExternalEntities|"
    r"javax\.xml\.stream\.isSupportingExternalEntities"
    r")"
)


def _strip_strings_and_comments(line: str) -> str:
    """Replace string-literal contents with spaces; drop ``//`` line comments.

    Java-flavoured: handles ``"..."`` and ``'.'`` char literals. Does not
    track ``/* ... */`` block comments across lines.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_c = False
    while i < n:
        ch = line[i]
        if in_s:
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
    """Mitigation regex is checked against the *raw* text on purpose.

    The Apache feature URIs and the boolean ``false`` literals appear
    inside string literals / argument expressions, which our line
    stripper would blank out. Checking raw text is the right call here.
    """
    return RE_MITIGATIONS.search(text) is not None


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    mitigated = _file_has_mitigations(text)
    if mitigated:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        stripped = _strip_strings_and_comments(raw)
        m = RE_RISKY_NEWINSTANCE.search(stripped)
        if m:
            findings.append(
                (path, lineno, f"xxe-{m.group(1)}-newInstance", raw.rstrip())
            )
            continue
        m2 = RE_RISKY_NEW_BUILDER.search(stripped)
        if m2:
            findings.append(
                (path, lineno, f"xxe-new-{m2.group(1)}", raw.rstrip())
            )
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.java")):
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
