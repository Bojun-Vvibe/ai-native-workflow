#!/usr/bin/env python3
"""
llm-output-ruby-yaml-load-detector

Flags Ruby source where untrusted YAML is parsed with YAML.load,
YAML.load_file, YAML.load_stream, Psych.load, or Psych.load_file
*without* explicit safe_mode wiring. These entry points instantiate
arbitrary Ruby objects and have a long history of being abused for
deserialization RCE (the classic Rails CVE-2013-0156 family,
RubyGems CVE-2017-0903, etc.). The safe form is YAML.safe_load
(or Psych.safe_load).

Stdlib only. Reads files passed on argv (or recurses into directories
for *.rb / *.rb.txt / *.erb). Exit 0 = no findings, 1 = finding(s),
2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Match YAML.load / YAML.load_file / YAML.load_stream and the
# equivalent Psych.* spellings. We deliberately do NOT match
# safe_load, safe_load_file, or safe_load_stream.
_LOAD_RE = re.compile(
    r"\b(?:YAML|Psych)\s*\.\s*"
    r"(?:load|load_file|load_stream|unsafe_load|unsafe_load_file)\b"
    r"\s*\("
)

# Allowlist marker: a permitted_classes:/aliases: kwarg on the SAME
# logical call line is treated as the user opting into the modern
# "safe-by-construction" Psych >= 4 form (load behaves like safe_load
# when permitted_classes is given). We accept that as not-a-finding.
_PERMITTED_KW = re.compile(r"\bpermitted_classes\s*:")


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        # ignore single-line comments
        code = line.split("#", 1)[0]
        if not _LOAD_RE.search(code):
            continue
        # Look at this line plus the next 2 for a permitted_classes kwarg.
        window = "\n".join(lines[i - 1 : i + 2])
        if _PERMITTED_KW.search(window):
            continue
        snippet = line.strip()
        if len(snippet) > 100:
            snippet = snippet[:97] + "..."
        findings.append(
            f"{path}:{i}: YAML.load / Psych.load on possibly untrusted "
            f"input (CWE-502): {snippet}"
        )
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    exts = (".rb", ".rb.txt", ".erb", ".rake", ".gemspec")
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(exts):
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
