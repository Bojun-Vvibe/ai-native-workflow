#!/usr/bin/env python3
"""Detect React JSX where `key={index}` (or the loop counter from a
.map((item, index) => ...) callback) is used as the React key.

Using the array index as a React key defeats reconciliation and causes
state-bleed bugs whenever the list reorders, has items inserted in
the middle, or filters items out. This is the single most common
React perf/correctness anti-pattern in LLM-generated tutorial code.

Stdlib only. Code-fence aware: handles ```jsx, ```tsx, ```js, ```ts
fenced blocks in markdown. Also runs directly on .jsx/.tsx/.js/.ts
files when no fences are detected.

Heuristics flagged:
  1. `key={index}` literal — direct use of a variable named index/idx/i
     as the key prop.
  2. `.map((item, idx) => ...)` callback whose body sets `key={idx}`
     where `idx` is the second parameter of the .map / .forEach /
     .flatMap callback.
  3. key={String(index)} / key={`${index}`} / key={index + ''}
     — coercion wrappers that don't change the underlying problem.

Comments and string literals are scrubbed before matching where
practical (we keep template literal interiors so we can still detect
them).

Prints findings as `path:line:col: msg`.
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, List, Tuple

JS_LANGS = {"jsx", "tsx", "js", "javascript", "ts", "typescript"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Strip "..." and '...' but NOT template literals — index inside
# `${index}` template literals is real and we want to flag it.
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Direct: key={index} / key={idx} / key={i}
DIRECT_KEY_RE = re.compile(
    r"\bkey\s*=\s*\{\s*(index|idx|i)\s*\}"
)
# Coerced: key={String(index)} / key={`${index}`} / key={index + ''}
COERCED_KEY_RE = re.compile(
    r"\bkey\s*=\s*\{\s*("
    r"String\s*\(\s*(?:index|idx|i)\s*\)"
    r"|`\$\{(?:index|idx|i)\}`"
    r"|(?:index|idx|i)\s*\+\s*['\"]['\"]"
    r"|(?:index|idx|i)\.toString\s*\(\s*\)"
    r")\s*\}"
)
# .map((item, idx) => ...) where idx is the second positional param.
# Capture the second param name. Allow optional type annotation
# `(item: T, idx: number)`.
MAP_CALLBACK_RE = re.compile(
    r"\.(?:map|forEach|flatMap|filter|reduce)\s*\(\s*"
    r"\(\s*\w+(?:\s*:\s*[^,]+)?\s*,\s*(\w+)(?:\s*:\s*[^,)]+)?\s*\)"
    r"\s*=>"
)
# Generic key={someVar} where someVar matches the captured callback param.
def key_uses_var_re(name: str):
    pattern = (
        r"\bkey\s*=\s*\{\s*("
        rf"{re.escape(name)}"
        rf"|String\(\s*{re.escape(name)}\s*\)"
        rf"|`\$\{{{re.escape(name)}\}}`"
        rf"|{re.escape(name)}\s*\+\s*['\"]['\"]"
        rf"|{re.escape(name)}\.toString\(\s*\)"
        r")\s*\}"
    )
    return re.compile(pattern)


def iter_jsx_blocks(lines: List[str]) -> Iterator[Tuple[int, List[str]]]:
    in_fence = False
    fence_marker = ""
    fence_indent = ""
    fence_lang = ""
    fence_start = 0
    body: List[str] = []
    saw_any_fence = False

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = FENCE_RE.match(line)
        if not in_fence:
            if m:
                saw_any_fence = True
                in_fence = True
                fence_indent = m.group(1)
                fence_marker = m.group(2)[0] * len(m.group(2))
                fence_lang = m.group(3).strip().lower()
                fence_start = i
                body = []
        else:
            stripped = line.lstrip()
            if (
                stripped.startswith(fence_marker[0])
                and set(stripped.rstrip()) <= {fence_marker[0]}
                and len(stripped.rstrip()) >= len(fence_marker)
            ):
                if fence_lang in JS_LANGS:
                    yield fence_start, body
                in_fence = False
                fence_marker = ""
                fence_lang = ""
                body = []
            else:
                if fence_indent and line.startswith(fence_indent):
                    body.append(line[len(fence_indent):])
                else:
                    body.append(line)
    if in_fence and fence_lang in JS_LANGS:
        yield fence_start, body
    if not saw_any_fence:
        yield 1, [l.rstrip("\n") for l in lines]


def scrub(line: str) -> str:
    line = STRING_RE.sub('""', line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def lint_block(start_line: int, body: List[str], path: str) -> int:
    body_text = "\n".join(body)
    body_text = BLOCK_COMMENT_RE.sub("", body_text)
    rebuilt = body_text.splitlines()

    findings = 0
    # Track callback param names that look index-like or were declared
    # in a .map(... , p) callback. Scope them to the next ~40 lines as
    # a cheap proxy for the callback body.
    pending_callbacks: List[Tuple[str, int]] = []  # (name, expires_at_index)

    for j, raw in enumerate(rebuilt):
        clean = scrub(raw)

        # Direct index/idx/i usage.
        for m in DIRECT_KEY_RE.finditer(clean):
            line_no = start_line + j
            col = m.start() + 1
            print(f"{path}:{line_no}:{col}: key={{{m.group(1)}}} uses array index as React key")
            findings += 1
        for m in COERCED_KEY_RE.finditer(clean):
            line_no = start_line + j
            col = m.start() + 1
            print(f"{path}:{line_no}:{col}: key uses index variable via coercion ({m.group(1)})")
            findings += 1

        # Register .map callback second-param.
        for m in MAP_CALLBACK_RE.finditer(clean):
            name = m.group(1)
            if name in {"index", "idx", "i"}:
                # Already covered by DIRECT_KEY_RE / COERCED_KEY_RE.
                continue
            pending_callbacks.append((name, j + 40))

        # Check pending callbacks against this line.
        live: List[Tuple[str, int]] = []
        for name, expiry in pending_callbacks:
            if j > expiry:
                continue
            kre = key_uses_var_re(name)
            for m in kre.finditer(clean):
                line_no = start_line + j
                col = m.start() + 1
                print(f"{path}:{line_no}:{col}: key uses .map callback index param '{name}' as React key")
                findings += 1
            live.append((name, expiry))
        pending_callbacks = live

    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detector.py <file>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total = 0
    for start, body in iter_jsx_blocks(lines):
        total += lint_block(start, body, path)
    print(f"total findings: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
