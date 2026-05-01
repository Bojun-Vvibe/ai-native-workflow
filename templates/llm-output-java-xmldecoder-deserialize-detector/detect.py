#!/usr/bin/env python3
"""
llm-output-java-xmldecoder-deserialize-detector

Flags Java code that constructs a `java.beans.XMLDecoder` from any
input stream and then calls `.readObject()`. `XMLDecoder` is a
Turing-complete deserializer: a crafted XML document can instantiate
arbitrary classes and invoke arbitrary methods (including
`Runtime.exec`). It must NEVER be used on untrusted input.

Why it's bad:
  XMLDecoder's `<object class="..."><void method="..."/>` grammar lets
  the attacker call any public method on any class on the classpath.
  Public PoCs reach RCE in three lines of XML. There is no allow-list
  mode, no resolveClass hook, no safe configuration. Mitigation =
  remove the call.

Maps to:
  - CWE-502: Deserialization of Untrusted Data
  - CWE-20:  Improper Input Validation

LLMs reach for this pattern because XMLDecoder is the symmetric
counterpart of XMLEncoder and shows up in every "persist a JavaBean
to disk" tutorial. Many of those tutorials then casually feed the
decoder a file path or HTTP body. We catch it.

Heuristic (stdlib only, scans *.java):

  Flag any file that contains BOTH:
    (1) `new XMLDecoder(`   (anywhere)
    (2) `.readObject(`      (anywhere in the same file)

  Also flag the fully-qualified form `new java.beans.XMLDecoder(`.

  We do NOT flag:
    - A file that imports XMLDecoder but never instantiates it.
    - A file that instantiates XMLDecoder but the instantiation is
      inside a `// ` line comment or `/* ... */` block comment.

Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = (".java",)

CTOR = re.compile(r"\bnew\s+(?:java\s*\.\s*beans\s*\.\s*)?XMLDecoder\s*\(")
READ = re.compile(r"\.\s*readObject\s*\(")

LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')


def strip_noise(src: str) -> str:
    src = BLOCK_COMMENT.sub("", src)
    src = LINE_COMMENT.sub("", src)
    src = STRING_LITERAL.sub('""', src)
    return src


def find_findings(src: str) -> List[Tuple[int, str]]:
    cleaned = strip_noise(src)
    ctor_hits = list(CTOR.finditer(cleaned))
    if not ctor_hits:
        return []
    if not READ.search(cleaned):
        return []
    out: List[Tuple[int, str]] = []
    for m in ctor_hits:
        line = cleaned[: m.start()].count("\n") + 1
        out.append(
            (line, "XMLDecoder constructed and readObject() called -- arbitrary code execution sink")
        )
    return out


def iter_files(args: Iterable[str]) -> Iterable[str]:
    for a in args:
        if os.path.isdir(a):
            for root, _, files in os.walk(a):
                for f in files:
                    if f.endswith(EXTS):
                        yield os.path.join(root, f)
        elif os.path.isfile(a):
            yield a


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file-or-dir> [<file-or-dir> ...]", file=sys.stderr)
        return 2
    any_finding = False
    for path in iter_files(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError as e:
            print(f"{path}: read error: {e}", file=sys.stderr)
            continue
        for line, msg in find_findings(src):
            any_finding = True
            print(f"{path}:{line}: {msg}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
