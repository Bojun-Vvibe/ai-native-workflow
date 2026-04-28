#!/usr/bin/env python3
"""
llm-output-rust-unwrap-in-library-detector

Flags `.unwrap()` and `.expect(...)` calls in Rust *library* source files
(i.e., `lib.rs` or modules reachable from a library crate). These calls
panic on `Err`/`None`, which is acceptable in binaries (`fn main()`) and
in tests, but in library code it converts a recoverable error into a
crash for every downstream caller.

Scope rules:
  * Skip files in any directory named `tests` (Cargo integration tests).
  * Skip files named `main.rs` (binary entry points).
  * Skip files matching `*_test.rs` / `*_tests.rs`.
  * Within a file, skip code inside `#[cfg(test)] mod ... { ... }`
    blocks and inside `fn main() { ... }`.
  * Mask comments and string/char literals before matching, so an
    `.unwrap()` mentioned inside `"..."`, `r"..."`, `r#"..."#`, `'..'`,
    `// ...`, or `/* ... */` does not trip.

Stdlib only. Single pass per file.

Exit codes:
  0  no hits
  1  one or more hits printed
  2  usage error
"""
from __future__ import annotations
import os
import sys
from typing import List, Tuple


def mask_line(src: str, in_block_comment: bool, raw_hashes: int) -> Tuple[str, bool, int]:
    """Mask comments + string/char literals on one line.

    `raw_hashes` carries state for an unterminated raw string `r#..#"..."#..#`
    that spans multiple lines: 0 means "not inside a raw string", >=0 with
    in_block_comment=False is overloaded — we instead use raw_hashes=-1 for
    "not in raw string" and >=0 for "inside raw string with this many `#`".
    """
    out: List[str] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        # raw string continuation
        if raw_hashes >= 0:
            if c == '"':
                # check trailing #'s
                k = 0
                while i + 1 + k < n and src[i + 1 + k] == "#":
                    k += 1
                if k >= raw_hashes:
                    out.append('"')
                    out.append("#" * raw_hashes)
                    i += 1 + raw_hashes
                    raw_hashes = -1
                    continue
            out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                out.append("  ")
                i += 2
                in_block_comment = False
            else:
                out.append(" ")
                i += 1
            continue
        # line comment
        if c == "/" and nxt == "/":
            out.append(" " * (n - i))
            break
        if c == "/" and nxt == "*":
            out.append("  ")
            i += 2
            in_block_comment = True
            continue
        # raw string r"..." or r#"..."#
        if c == "r" and (nxt == '"' or nxt == "#"):
            # count hashes
            j = i + 1
            hashes = 0
            while j < n and src[j] == "#":
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                # entered raw string
                out.append(" " * (j - i + 1))
                i = j + 1
                # consume until matching "###...
                terminated = False
                while i < n:
                    if src[i] == '"':
                        k = 0
                        while i + 1 + k < n and src[i + 1 + k] == "#":
                            k += 1
                        if k >= hashes:
                            out.append('"' + "#" * hashes)
                            i += 1 + hashes
                            terminated = True
                            break
                    out.append(" ")
                    i += 1
                if not terminated:
                    raw_hashes = hashes
                continue
        # regular string "..."
        if c == '"':
            out.append('"')
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == '"':
                    out.append('"')
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        # char literal '.' or '\n' — careful not to eat lifetimes 'a
        if c == "'":
            # peek: lifetime is 'ident (no closing quote within 1-2 chars)
            # Heuristic: a char literal is '<one or escaped>'  closing within 4 chars.
            # If we don't see a closing ' within 4 chars, treat as lifetime.
            close = -1
            j = i + 1
            # allow escape
            if j < n and src[j] == "\\":
                # \x.., \u{..}, \n, etc — look up to 8 chars
                for k in range(j + 1, min(j + 10, n)):
                    if src[k] == "'":
                        close = k
                        break
            else:
                # one char then closing quote
                if j + 1 < n and src[j + 1] == "'":
                    close = j + 1
            if close > 0:
                out.append("'")
                out.append(" " * (close - i - 1))
                out.append("'")
                i = close + 1
                continue
            # treat as lifetime — keep as-is (single quote then ident)
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out), in_block_comment, raw_hashes


def is_word_boundary_left(s: str, idx: int) -> bool:
    if idx <= 0:
        return True
    p = s[idx - 1]
    return not (p.isalnum() or p == "_")


def find_calls(masked: str) -> List[Tuple[int, str]]:
    """Return list of (col, kind) for `.unwrap(` and `.expect(` occurrences."""
    hits: List[Tuple[int, str]] = []
    for kw in ("unwrap", "expect"):
        needle = "." + kw
        start = 0
        while True:
            j = masked.find(needle, start)
            if j == -1:
                break
            # left boundary: char before `.` should not be alnum/_/. (avoid f64.unwrap chains? still flag)
            # we accept anything before the dot
            after = j + len(needle)
            # next non-space must be `(`
            k = after
            while k < len(masked) and masked[k] == " ":
                k += 1
            if k < len(masked) and masked[k] == "(":
                # ensure right boundary on the keyword
                end = j + len(needle)
                if end >= len(masked) or not (masked[end].isalnum() or masked[end] == "_"):
                    hits.append((j, kw))
            start = j + 1
    return hits


def should_skip_file(path: str) -> bool:
    base = os.path.basename(path)
    if base == "main.rs":
        return True
    if base.endswith("_test.rs") or base.endswith("_tests.rs"):
        return True
    parts = path.replace("\\", "/").split("/")
    if "tests" in parts:
        return True
    return False


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    if should_skip_file(path):
        return []
    lines = text.splitlines()

    # First pass: mask lines so we can analyze structure cleanly.
    masked_lines: List[str] = []
    in_block = False
    raw_h = -1
    for raw in lines:
        m, in_block, raw_h = mask_line(raw, in_block, raw_h)
        masked_lines.append(m)

    # Second pass: track scope stack with kinds we care about:
    #   "main"        — body of `fn main`
    #   "cfg_test"    — body of `#[cfg(test)] mod ... { ... }`
    #   "block"       — anything else
    # We push on `{`, pop on `}`. The "pending kind" for the next `{`
    # is set when we see `fn main` or `#[cfg(test)]` followed by `mod`.
    scope: List[str] = []
    pending: List[str] = []
    cfg_test_armed = False  # saw `#[cfg(test)]` recently (for next `mod`/`fn`/`{`)

    hits: List[Tuple[int, str]] = []

    for ln, m in enumerate(masked_lines, 1):
        # detect attribute lines like `#[cfg(test)]` (on their own line typically)
        stripped = m.strip()
        # very tolerant cfg(test) recognition
        if "#[cfg(test)]" in m or "#[cfg(all(test" in m or "#[cfg(any(test" in m:
            cfg_test_armed = True

        # Look for `fn main` token followed eventually by `{` — we set a pending kind
        # only when the `(` of `main(` appears.
        # Simple approach: if line contains `fn main(` mark pending "main".
        if "fn main(" in m or m.rstrip().endswith("fn main"):
            pending.append("main")

        # If cfg_test_armed and we see `mod ` then `{`, the next `{` is cfg_test.
        if cfg_test_armed and ("mod " in m or "mod\t" in m):
            pending.append("cfg_test")
            cfg_test_armed = False
        elif cfg_test_armed and "fn " in m:
            # `#[cfg(test)] fn foo() { ... }` — entire fn is test-only
            pending.append("cfg_test")
            cfg_test_armed = False

        # Walk the line char by char to handle braces and call-sites in order.
        events: List[Tuple[int, str]] = []
        for idx, ch in enumerate(m):
            if ch == "{":
                events.append((idx, "lbrace"))
            elif ch == "}":
                events.append((idx, "rbrace"))
        for col, kw in find_calls(m):
            events.append((col, "call:" + kw))
        events.sort(key=lambda x: x[0])

        for col, kind in events:
            if kind == "lbrace":
                if pending:
                    scope.append(pending.pop(0))
                else:
                    scope.append("block")
            elif kind == "rbrace":
                if scope:
                    scope.pop()
            elif kind.startswith("call:"):
                kw = kind.split(":", 1)[1]
                # Suppress if any ancestor is `main` or `cfg_test`.
                if "main" in scope or "cfg_test" in scope:
                    continue
                hits.append((ln, f".{kw}() in library code: panics on Err/None"))

        # If line had no `{` but a pending was set speculatively (e.g. a stray
        # `fn main` token in a doc string we missed), it will sit on the
        # pending stack until the next `{`. That's acceptable for this simple
        # detector — the worst case is a slight scope mis-attribution in
        # adversarial inputs.

    return hits


def iter_rust_files(root: str):
    if os.path.isfile(root):
        if root.endswith(".rs"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "target", "node_modules")]
        for fn in filenames:
            if fn.endswith(".rs"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_rust_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
