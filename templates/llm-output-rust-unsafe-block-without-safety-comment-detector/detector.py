#!/usr/bin/env python3
"""Detect Rust ``unsafe { ... }`` blocks that are not preceded by a
``// SAFETY:`` (or ``/* SAFETY: */``) justification comment.

Background:
  Rust's ``unsafe`` keyword tells the compiler "trust me, I have
  manually verified the invariants the safe surface couldn't prove".
  The community-accepted convention (codified in the Rust API
  guidelines, ``clippy::undocumented_unsafe_blocks``, and the
  ``std`` library style guide) is that **every** ``unsafe { ... }``
  block must be immediately preceded by a comment of the form
  ``// SAFETY: <why this is sound>``.

  LLMs writing Rust frequently emit ``unsafe { ... }`` blocks that
  bypass borrow-check / type-safety / pointer-validity guarantees
  without any soundness justification. This detector flags those
  cases so a human can decide whether the unsafety is actually
  warranted (and, if so, document it).

What's checked:
  - Each ``unsafe`` followed by ``{`` on the same logical line is
    treated as an unsafe BLOCK (this is the form the convention
    targets — ``unsafe fn``, ``unsafe trait``, ``unsafe impl`` are
    declarations, not blocks, and intentionally NOT flagged).
  - The preceding non-blank, non-attribute line(s) (skipping ``#[...]``
    attributes) must contain ``SAFETY:`` (case-sensitive, allowing
    ``// SAFETY:`` or ``/* SAFETY:`` styles, optionally followed by
    text on the same or following line).
  - A ``// SAFETY:`` comment **on the same line** as the ``unsafe``
    keyword (trailing comment style) is also accepted.
  - ``unsafe`` inside string literals or line comments is ignored
    via a simple string/comment-aware tokenizer pass.

CWE refs (when the unsafety is actually a bug — these guide reviewer
attention):
  - CWE-119: Improper Restriction of Operations within the Bounds of
    a Memory Buffer
  - CWE-416: Use After Free
  - CWE-787: Out-of-bounds Write
  - CWE-1265: Unintended Reentrant Invocation of Non-reentrant Code

False-positive surface:
  - Generated code (``mod ffi;`` from ``bindgen``) — suppress per
    file with a comment ``// rust-unsafe-audit-skip`` anywhere in
    the file.
  - Macro-generated unsafe (e.g. ``some_macro! { unsafe { ... } }``)
    — the macro authors should document at the macro call site.
  - ``unsafe fn`` / ``unsafe trait`` / ``unsafe impl`` declarations
    are intentionally NOT flagged (the convention applies to the
    callers of unsafe, not to declarations).

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"rust-unsafe-audit-skip")

# Strip line comments and block comments and string contents (keeping
# line-count alignment by replacing chars with spaces).
def _strip_strings_and_comments(src: str) -> str:
    out = []
    i = 0
    n = len(src)
    in_line_comment = False
    in_block_comment = False
    in_str = False
    str_q = ""
    in_raw_str = False
    raw_hashes = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
                out.append(c)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                out.append("  ")
                i += 2
                continue
            out.append(" " if c != "\n" else "\n")
            i += 1
            continue
        if in_raw_str:
            if c == '"':
                # need this many '#' after
                j = i + 1
                hashes = 0
                while j < n and src[j] == "#" and hashes < raw_hashes:
                    hashes += 1
                    j += 1
                if hashes == raw_hashes:
                    in_raw_str = False
                    out.append(" " * (j - i))
                    i = j
                    continue
            out.append(" " if c != "\n" else "\n")
            i += 1
            continue
        if in_str:
            if c == "\\" and nxt:
                out.append("  ")
                i += 2
                continue
            if c == str_q:
                in_str = False
                out.append(" ")
                i += 1
                continue
            out.append(" " if c != "\n" else "\n")
            i += 1
            continue
        # not inside any
        if c == "/" and nxt == "/":
            in_line_comment = True
            out.append("  ")
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            out.append("  ")
            i += 2
            continue
        if c == "r" and i + 1 < n and (src[i + 1] == '"' or src[i + 1] == "#"):
            # raw string: r#*"
            j = i + 1
            hashes = 0
            while j < n and src[j] == "#":
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                in_raw_str = True
                raw_hashes = hashes
                out.append(" " * (j - i + 1))
                i = j + 1
                continue
        if c == '"' or c == "'":
            # Rust char literal vs lifetime: lifetimes are 'a, 'static — no closing
            # We'll heuristically only enter string mode for '"'. Char literals
            # rarely contain "unsafe" so we skip them.
            if c == '"':
                in_str = True
                str_q = c
                out.append(" ")
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


UNSAFE_BLOCK_RE = re.compile(r"\bunsafe\b\s*\{")
DECL_PREFIX_RE = re.compile(r"\bunsafe\s+(fn|trait|impl|extern)\b")


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    stripped = _strip_strings_and_comments(source)
    raw_lines = source.splitlines()

    for m in UNSAFE_BLOCK_RE.finditer(stripped):
        # Compute line number (1-indexed) of the `unsafe` token.
        line_no = stripped.count("\n", 0, m.start()) + 1

        # Skip if the same offset starts an `unsafe fn|trait|impl|extern`
        # declaration. (UNSAFE_BLOCK_RE requires `{` directly after, but
        # `unsafe extern "C" { ... }` would also match — guard explicitly.)
        # Look at the original line for the declaration form.
        orig_line = raw_lines[line_no - 1] if line_no - 1 < len(raw_lines) else ""
        if DECL_PREFIX_RE.search(orig_line):
            continue

        # Look for `SAFETY:` either on the same original line OR on the
        # nearest preceding non-blank, non-attribute line in the original
        # source.
        if "SAFETY:" in orig_line:
            continue

        found_safety = False
        j = line_no - 2  # 0-indexed previous line
        while j >= 0:
            prev = raw_lines[j].strip()
            if not prev:
                j -= 1
                continue
            if prev.startswith("#["):
                j -= 1
                continue
            # Walk over a contiguous run of comment lines looking for SAFETY:
            if prev.startswith("//") or prev.startswith("/*") or prev.startswith("*"):
                if "SAFETY:" in prev:
                    found_safety = True
                    break
                j -= 1
                continue
            # First non-comment, non-attribute, non-blank line — stop.
            break

        if not found_safety:
            findings.append((
                line_no,
                "unsafe { ... } block missing `// SAFETY:` justification "
                "comment on the preceding line",
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.rs")))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
