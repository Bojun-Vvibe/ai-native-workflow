#!/usr/bin/env python3
"""
llm-output-javascript-prototype-pollution-detector

Flags JavaScript / TypeScript code that performs an unsafe recursive
merge / clone / setNested-by-path operation in a way that lets an
attacker-controlled key reach `Object.prototype`.

Why it's bad:
  Any property assignment of the form
      target[key1][key2] = value
  where `key1` came from JSON / a query string / a request body and
  the merge logic does NOT block the keys "__proto__", "constructor",
  or "prototype" lets an attacker poison `Object.prototype` for the
  whole process. Subsequent code that relies on default-undefined
  properties (`if (!user.isAdmin)`, `if (!opts.shell)`) becomes
  vulnerable.

Maps to:
  - CWE-1321: Improperly Controlled Modification of Object Prototype
              Attributes ("Prototype Pollution")
  - CWE-915:  Improperly Controlled Modification of Dynamically-
              Determined Object Attributes

LLMs reach for this pattern because every "deepMerge" / "set by dotted
path" snippet on the open web ships the unsafe version. We catch it.

Heuristic (stdlib only, scans *.js / *.ts / *.mjs / *.cjs / *.tsx /
*.jsx):

  Flag if a file matches BOTH:
    (A) An assignment whose left-hand side uses a computed key that
        was *not* validated against {"__proto__", "constructor",
        "prototype"}, e.g.:
            obj[key] = ...
            obj[parts[i]] = ...
            current[k][k2] = ...
        inside a function body that walks an input.
    (B) The function body contains at least one of the unsafe
        idioms:
            for (const key in src)        // recursive merge over input
            Object.keys(src).forEach
            JSON.parse(...)               // building target from input
            split('.')                    // dotted-path setter
        AND no guard like:
            key === '__proto__'
            key === 'constructor'
            key === 'prototype'
            Object.prototype.hasOwnProperty
            Object.create(null)

  Also flag direct writes:
            obj['__proto__'].polluted = ...
            obj.__proto__[x] = ...
            target.constructor.prototype.x = ...

Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = (".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx")

# Direct pollution writes -- always flag.
DIRECT_PATTERNS = [
    re.compile(r"""\[\s*['"]__proto__['"]\s*\]"""),
    re.compile(r"""\.__proto__\b\s*\["""),
    re.compile(r"""\.__proto__\s*\.\s*\w+\s*="""),
    re.compile(r"""\.constructor\s*\.\s*prototype\s*\["""),
    re.compile(r"""\.constructor\s*\.\s*prototype\s*\.\s*\w+\s*="""),
]

# Indirect: a recursive-merge or dotted-path-set function body.
RECURSIVE_HEURISTICS = [
    re.compile(r"\bfor\s*\(\s*(?:const|let|var)\s+\w+\s+in\s+\w+\s*\)"),
    re.compile(r"\bObject\.keys\s*\(\s*\w+\s*\)\s*\.\s*forEach\b"),
    re.compile(r"""\.split\s*\(\s*['"]\.['"]\s*\)"""),
]

# Computed-key write that traverses input.
COMPUTED_WRITE = re.compile(r"""\b\w+\s*\[\s*\w+(?:\[\s*\w+\s*\])?\s*\]\s*(?:\[\s*\w+\s*\])?\s*=""")

# Guards that, if present, suppress the indirect finding.
GUARD_PATTERNS = [
    re.compile(r"""['"]__proto__['"]"""),
    re.compile(r"""['"]constructor['"]"""),
    re.compile(r"""['"]prototype['"]"""),
    re.compile(r"\bObject\.create\s*\(\s*null\s*\)"),
    re.compile(r"\bMap\s*\(\s*\)"),  # using Map instead of plain obj
    re.compile(r"\bhasOwnProperty\.call\b"),
    re.compile(r"\bObject\.hasOwn\b"),
    re.compile(r"\b__proto__\b\s*[!=]==?"),
]

LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(src: str) -> str:
    src = BLOCK_COMMENT.sub("", src)
    src = LINE_COMMENT.sub("", src)
    return src


def find_findings(path: str, src: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    cleaned = strip_comments(src)

    # (1) Direct pollution writes.
    for pat in DIRECT_PATTERNS:
        for m in pat.finditer(cleaned):
            line = cleaned[: m.start()].count("\n") + 1
            out.append((line, "direct write to __proto__/constructor.prototype"))

    # (2) Indirect: recursive-merge / dotted-path setter without guard.
    has_recursive = any(p.search(cleaned) for p in RECURSIVE_HEURISTICS)
    has_write = COMPUTED_WRITE.search(cleaned)
    has_guard = any(p.search(cleaned) for p in GUARD_PATTERNS)

    if has_recursive and has_write and not has_guard:
        # Report on the first recursive-iteration line.
        for p in RECURSIVE_HEURISTICS:
            m = p.search(cleaned)
            if m:
                line = cleaned[: m.start()].count("\n") + 1
                out.append(
                    (line, "recursive merge / dotted-path setter without __proto__ guard")
                )
                break

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
        print(
            "usage: detect.py <file-or-dir> [<file-or-dir> ...]",
            file=sys.stderr,
        )
        return 2

    any_finding = False
    for path in iter_files(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError as e:
            print(f"{path}: read error: {e}", file=sys.stderr)
            continue
        for line, msg in find_findings(path, src):
            any_finding = True
            print(f"{path}:{line}: {msg}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
