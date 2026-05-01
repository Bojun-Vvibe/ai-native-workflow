#!/usr/bin/env python3
"""
llm-output-csharp-binaryformatter-deserialize-detector

Flags C# source that calls `BinaryFormatter.Deserialize(...)` (or any
of its known-dangerous siblings: `NetDataContractSerializer`,
`SoapFormatter`, `LosFormatter`, `ObjectStateFormatter`). Calling
.Deserialize on attacker-controlled bytes lets the attacker choose the
runtime type to instantiate, which has historically led to RCE chains
in .NET (see ysoserial.net). The .NET team has marked
BinaryFormatter as obsolete and unsafe and is removing it from .NET.

LLMs still emit `new BinaryFormatter().Deserialize(stream)` because it
is the shortest "save/load object" snippet from circa-2010 tutorials.
This detector catches those.

Heuristic (stdlib-only, regex-based, no Roslyn):

  1. Find any of the dangerous formatter type names.
  2. On the same logical statement (joined across newlines until `;`),
     look for `.Deserialize(` -- that is the dangerous call.
  3. Emit a finding with file:line and the matched type.

We do NOT flag `JsonSerializer.Deserialize`, `XmlSerializer`, or
`DataContractJsonSerializer` -- those have their own (different)
risks and are out of scope for this detector.

Stdlib only. Reads files passed on argv (or recurses into dirs and
picks `*.cs` / `*.cshtml`). Exit 0 = no findings, 1 = at least one
finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

DANGEROUS_TYPES = (
    "BinaryFormatter",
    "NetDataContractSerializer",
    "SoapFormatter",
    "LosFormatter",
    "ObjectStateFormatter",
)

# Match the type name as a whole word (so we don't snag MyBinaryFormatter2).
_TYPE_RE = re.compile(
    r"\b(" + "|".join(DANGEROUS_TYPES) + r")\b"
)
_DESERIALIZE_RE = re.compile(r"\.Deserialize\s*\(")
_LINE_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(src: str) -> str:
    """Strip // and /* */ comments without disturbing line numbers for
    later mapping. We replace each comment with spaces of the same length
    so offsets stay aligned."""
    def _blank(m: "re.Match[str]") -> str:
        return "".join("\n" if c == "\n" else " " for c in m.group(0))

    src = _BLOCK_COMMENT_RE.sub(_blank, src)
    src = _LINE_COMMENT_RE.sub(_blank, src)
    return src


def _line_of(offset: int, src: str) -> int:
    return src.count("\n", 0, offset) + 1


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    cleaned = _strip_comments(text)
    # Walk every dangerous type mention and check the surrounding statement
    # (from the type position out to the next `;` or EOF) for `.Deserialize(`.
    for m in _TYPE_RE.finditer(cleaned):
        type_name = m.group(1)
        start = m.start()
        end_semicolon = cleaned.find(";", start)
        end = end_semicolon if end_semicolon != -1 else len(cleaned)
        # Also look a bit backwards in case the formatter was assigned to a
        # variable on a prior statement and Deserialize is on the next line;
        # that pattern is handled by the variable-tracking pass below.
        window = cleaned[start:end]
        if _DESERIALIZE_RE.search(window):
            lineno = _line_of(start, cleaned)
            findings.append(
                f"{path}:{lineno}: dangerous deserialization "
                f"({type_name}.Deserialize) -- CWE-502, allows arbitrary "
                f"type instantiation; do not use on untrusted input"
            )

    # Variable-tracking pass: catch
    #   var f = new BinaryFormatter();
    #   ...
    #   f.Deserialize(stream);
    var_decl_re = re.compile(
        r"\b(?:var|" + "|".join(DANGEROUS_TYPES) + r")\s+"
        r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*="
        r"\s*new\s+(?P<type>" + "|".join(DANGEROUS_TYPES) + r")\s*\("
    )
    for m in var_decl_re.finditer(cleaned):
        name = m.group("name")
        type_name = m.group("type")
        decl_line = _line_of(m.start(), cleaned)
        # Look for `<name>.Deserialize(` after this point.
        call_re = re.compile(r"\b" + re.escape(name) + r"\.Deserialize\s*\(")
        for cm in call_re.finditer(cleaned, m.end()):
            lineno = _line_of(cm.start(), cleaned)
            findings.append(
                f"{path}:{lineno}: dangerous deserialization "
                f"({type_name}.Deserialize via variable '{name}' "
                f"declared at line {decl_line}) -- CWE-502"
            )

    # Dedupe while preserving order (the two passes can overlap when
    # someone writes `new BinaryFormatter().Deserialize(s)` AND assigns).
    seen = set()
    uniq: List[str] = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(".cs") or f.endswith(".cshtml"):
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
