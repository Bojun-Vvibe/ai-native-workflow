#!/usr/bin/env python3
"""Detect dangerous dynamic-eval patterns in Scala source.

Scala 2/3 ship `scala.tools.reflect.ToolBox`, which compiles and runs
arbitrary Scala source at runtime. LLM-generated Scala code reaches for
this when asked to "make rules user-configurable" or "let users plug in
expressions" — a textbook RCE sink.

Sinks we flag:
  - import scala.tools.reflect.ToolBox          (capability acquisition)
  - <something>.mkToolBox(...)                  (constructs a toolbox)
  - <toolbox>.eval(<tree>)                      (executes code)
  - <toolbox>.compile(<tree>)                   (compiles code; the
                                                 returned thunk is the
                                                 exec step)
  - <toolbox>.parse("..." )                     (parses source string)

`parse` alone is "just parse", but the LLM idiom `tb.eval(tb.parse(s))`
turns attacker-controlled `s` into running code. Flagging both halves
(`parse` and `eval`/`compile`) gives reviewers either side of the chain.

We also flag `mkToolBox` / `import ... ToolBox` because they are the
capability-acquisition step; without them the eval/compile/parse calls
above would not refer to the dangerous API.

Single-pass, stdlib-only, with comment + string-literal masking.

Scala lexical context handled by the masker:
  - // line comments
  - /* ... */ block comments — Scala block comments DO nest, and the
    masker honours that nesting
  - "..." double-quoted strings with \\ escapes
  - \"\"\" triple-quoted raw strings (no escape processing; ends at the
    next \"\"\")
  - 'x' character literals (single-quoted)

Usage:
    python3 detect.py <file-or-dir> [<file-or-dir> ...]

Exit code = number of findings (capped at 255).
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # import scala.tools.reflect.ToolBox  (also: ToolBox._)
    ("import-ToolBox", re.compile(
        r"\bimport\s+scala\.tools\.reflect\.(?:ToolBox|\{[^}]*ToolBox[^}]*\})"
    )),
    # mkToolBox(...) — typically on currentMirror or a Mirror instance
    ("mkToolBox", re.compile(r"\bmkToolBox\s*\(")),
    # <expr>.eval(...)  — receiver is implicit; we conservatively flag any .eval(
    # on a line that also names ToolBox / tb / toolbox / mirror (heuristic) OR
    # appears next to .parse/.compile.
    ("toolbox-eval", re.compile(r"\.eval\s*\(")),
    # <expr>.compile(...)
    ("toolbox-compile", re.compile(r"\.compile\s*\(")),
    # <expr>.parse("..." or string)  — Scala reflect Toolbox parse
    ("toolbox-parse", re.compile(r"\.parse\s*\(")),
]

# A line/window must contain one of these tokens for `.eval(`, `.compile(`,
# `.parse(` to be reported. This filters out `Future.eval`, `regex.compile`,
# JSON `parse`, etc. that are not the reflect Toolbox.
_TB_CONTEXT = re.compile(
    r"\b(?:ToolBox|toolbox|toolBox|tb|mirror|currentMirror|cm|"
    r"reflect\.runtime|scala\.tools\.reflect)\b"
)

# These three patterns are gated by _TB_CONTEXT presence on the same line
# OR within the previous 4 lines (to handle multi-line chains like
#     val tb = currentMirror.mkToolBox()
#     val tree = tb.parse(src)
#     tb.eval(tree)
# ).
_GATED = {"toolbox-eval", "toolbox-compile", "toolbox-parse"}


def _mask(src: str) -> str:
    """Replace comment and string contents with spaces (preserving newlines)."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        # // line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
            continue
        # /* ... */ nesting block comment
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = i + 2
            depth = 1
            while j < n and depth > 0:
                if j + 1 < n and src[j] == "/" and src[j + 1] == "*":
                    depth += 1
                    j += 2
                    continue
                if j + 1 < n and src[j] == "*" and src[j + 1] == "/":
                    depth -= 1
                    j += 2
                    continue
                j += 1
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        # """ triple-quoted raw string """
        if c == '"' and i + 2 < n and src[i + 1] == '"' and src[i + 2] == '"':
            j = i + 3
            while j < n:
                if j + 2 < n and src[j] == '"' and src[j + 1] == '"' and src[j + 2] == '"':
                    j += 3
                    break
                j += 1
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        # "..." string with \ escape
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == '"':
                    j += 1
                    break
                if src[j] == "\n":
                    break  # malformed; bail
                j += 1
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        # 'x' or '\n' character literal — only mask if it really is a 1-char
        # literal; otherwise it could be a Scala 2 symbol like 'foo (rare in
        # modern code but valid). Conservative rule: only mask if we see
        # ' . ' (with a single char or escape between).
        if c == "'" and i + 2 < n:
            if src[i + 1] == "\\" and i + 3 < n and src[i + 3] == "'":
                out.append("    ")
                i += 4
                continue
            if src[i + 2] == "'":
                out.append("   ")
                i += 3
                continue
        out.append(c)
        i += 1
    return "".join(out)


def scan(path: str, src: str) -> List[Tuple[str, int, str, str]]:
    masked = _mask(src)
    masked_lines = masked.splitlines()
    src_lines = src.splitlines()

    line_starts = [0]
    for idx, ch in enumerate(src):
        if ch == "\n":
            line_starts.append(idx + 1)

    def lineno_for(offset: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def has_context(ln_idx: int) -> bool:
        # check this line and previous 4 lines (in masked text — TB tokens
        # are normal identifiers and would not have been masked away)
        start = max(0, ln_idx - 4)
        window = "\n".join(masked_lines[start : ln_idx + 1])
        return bool(_TB_CONTEXT.search(window))

    findings: List[Tuple[str, int, str, str]] = []
    seen = set()
    for name, pat in _PATTERNS:
        for m in pat.finditer(masked):
            ln = lineno_for(m.start())
            if name in _GATED and not has_context(ln - 1):
                continue
            key = (m.start(), name)
            if key in seen:
                continue
            line_text = src_lines[ln - 1] if ln - 1 < len(src_lines) else ""
            findings.append((path, ln, name, line_text.strip()))
            seen.add(key)
    findings.sort(key=lambda t: (t[0], t[1], t[2]))
    return findings


def iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if f.endswith((".scala", ".sc")):
                    yield os.path.join(dirpath, f)


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detect.py <file-or-dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_files(argv):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"{path}: skip ({e})", file=sys.stderr)
            continue
        for p, ln, name, txt in scan(path, src):
            print(f"{p}:{ln}: scala-toolbox-eval[{name}]: {txt}")
            total += 1
    print(f"--- {total} finding(s) ---", file=sys.stderr)
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
