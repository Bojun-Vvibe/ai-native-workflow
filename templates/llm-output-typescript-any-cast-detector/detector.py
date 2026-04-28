#!/usr/bin/env python3
"""
llm-output-typescript-any-cast-detector

Flags `as any` and `<any>` type assertions in TypeScript source
(`.ts` / `.tsx`). LLMs reach for `as any` to silence the type checker
when they don't fully understand a type, which defeats the entire
purpose of using TypeScript.

Detected forms:
  * `expr as any`     — `as` keyword cast to `any`
  * `<any>expr`       — angle-bracket cast (legal in `.ts`; not `.tsx`)
  * `as any[]`, `as any | null`, `as readonly any[]`  — counted as
    `as any` because the leading `any` is what suppresses checks.

Masked / ignored:
  * Comments: `// ...`, `/* ... */`
  * String literals: `"..."`, `'...'`, backtick template literals
    including `${...}` interpolation (we mask the literal text but
    recurse into interpolations).
  * Files in `__tests__/` directories.
  * Files matching `*.test.ts`, `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`.

Stdlib only, single pass per file.

Exit codes:
  0  no hits
  1  one or more hits printed
  2  usage error
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


def mask_source(text: str) -> str:
    """Mask comments and string/template literal contents.

    Returns text of the same length where masked characters are spaces
    (newlines preserved) so line numbers and column offsets are
    unchanged for downstream regex matching.
    """
    out = list(text)
    n = len(text)
    i = 0
    # template-literal nesting: when inside `...${...}...` we must
    # treat the contents of ${...} as code (which itself can contain
    # strings or templates). We track a stack of "what closes me":
    # entries are 'tmpl' (a backtick) or 'interp' (a `}` for ${...}).
    stack: List[str] = []
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        top = stack[-1] if stack else None

        # Inside a template literal raw section
        if top == "tmpl":
            if c == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " "
                i += 2
                continue
            if c == "$" and nxt == "{":
                # exit raw section, enter interpolation (code)
                # leave `${` un-masked so brace balance shows
                out[i] = " "
                out[i + 1] = " "
                stack.append("interp")
                i += 2
                continue
            if c == "`":
                # close template
                stack.pop()
                # leave backtick visible
                i += 1
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue

        # Inside ${...} we treat as code; track braces so we know when ` resumes.
        if top == "interp":
            if c == "{":
                stack.append("brace")
            elif c == "}":
                stack.pop()  # pop the interp
            # else fall through to general code handling below
            # but we still need to handle strings/comments inside interp
            # so don't `continue` — process this char as code:

        # general code mode
        if c == "/" and nxt == "/":
            # line comment to end of line
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
            continue
        if c == "/" and nxt == "*":
            out[i] = " "
            out[i + 1] = " "
            j = i + 2
            while j + 1 < n and not (text[j] == "*" and text[j + 1] == "/"):
                if text[j] != "\n":
                    out[j] = " "
                j += 1
            if j + 1 < n:
                out[j] = " "
                out[j + 1] = " "
                j += 2
            i = j
            continue
        if c == '"' or c == "'":
            quote = c
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    continue
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                i += 1  # consume closing quote
            continue
        if c == "`":
            # entering template literal
            stack.append("tmpl")
            i += 1
            continue
        # If we just popped an interp above, we already advanced past the `}`.
        # But we still need to advance i for normal code chars.
        if top == "interp" and c == "}":
            i += 1
            continue
        if top == "interp" and c == "{":
            i += 1
            continue
        i += 1

    return "".join(out)


# `as any` followed by a non-identifier char (so `as anyone` doesn't trip).
RE_AS_ANY = re.compile(r"\bas\s+any\b(?![\w$])")
# `<any>` cast: `<any>expr`. Avoid generic `Array<any>` style — that's a
# *use* of `any`, not a cast that suppresses an inferred type. The cast
# form is identifiable by being preceded by `=`, `(`, `,`, `return`, `:`
# whitespace etc., and followed immediately by an identifier or `(`.
RE_ANGLE_ANY = re.compile(r"(?<![\w$])<\s*any\s*>(?=[\s\(\[\w$\"'`])")


def should_skip_file(path: str) -> bool:
    norm = path.replace("\\", "/")
    base = os.path.basename(norm)
    if "/__tests__/" in norm or norm.endswith("/__tests__"):
        return True
    for suf in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"):
        if base.endswith(suf):
            return True
    return False


def scan_file(path: str) -> List[Tuple[int, str]]:
    if should_skip_file(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    masked = mask_source(text)
    hits: List[Tuple[int, str]] = []
    # build line offsets
    line_starts = [0]
    for idx, ch in enumerate(masked):
        if ch == "\n":
            line_starts.append(idx + 1)

    def lineno(pos: int) -> int:
        # binary search
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for m in RE_AS_ANY.finditer(masked):
        hits.append((lineno(m.start()), "`as any` cast: suppresses type checking"))
    # Angle-bracket cast only valid in .ts (not .tsx where `<x>` is JSX).
    if not path.endswith(".tsx"):
        for m in RE_ANGLE_ANY.finditer(masked):
            hits.append((lineno(m.start()), "`<any>` cast: suppresses type checking"))
    hits.sort()
    return hits


def iter_ts_files(root: str):
    if os.path.isfile(root):
        if root.endswith(".ts") or root.endswith(".tsx"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "dist", "build")]
        for fn in filenames:
            if fn.endswith(".ts") or fn.endswith(".tsx"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_ts_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
