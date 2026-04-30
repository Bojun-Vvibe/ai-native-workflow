#!/usr/bin/env python3
"""Detect JWT verification bypass patterns in Python source.

LLMs asked to "decode this JWT" routinely produce snippets that
either disable signature verification entirely or accept the
`none` algorithm. Both reduce a signed token to a plain JSON blob
that any caller can forge.

What this flags
---------------
* `jwt.decode(..., verify=False)`              (PyJWT < 2.0 API)
* `jwt.decode(..., options={"verify_signature": False, ...})`
* `jwt.decode(..., algorithms=["none"])`        (case-insensitive)
* `jwt.decode(..., algorithms=["HS256", "none"])` (any list elem)
* `jwt.decode(..., algorithm="none")`           (singular kwarg)
* `jwt.decode(..., algorithms=None)`             (PyJWT treats as "no check")
* Bare `decode(...)` calls with the same patterns where preceded
  by `from jwt import decode` (we keep this dumb on purpose:
  call name `decode` plus any of the bad kwargs).

What this does NOT flag
-----------------------
* `jwt.decode(token, key, algorithms=["HS256"])`  — explicit alg list
* `jwt.decode(..., options={"verify_signature": True})`
* Lines marked with a trailing `# jwt-decode-ok` comment.
* Occurrences inside `#` comments or string / docstring literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_DECODE = re.compile(r"\b(?:jwt\s*\.\s*)?decode\s*\(")
RE_VERIFY_FALSE = re.compile(r"\bverify\s*=\s*False\b")
RE_VERIFY_SIG_FALSE = re.compile(
    r"""['"]verify_signature['"]\s*:\s*False\b"""
)
RE_ALG_SINGULAR_NONE = re.compile(
    r"""\balgorithm\s*=\s*['"]\s*none\s*['"]""",
    re.IGNORECASE,
)
RE_ALGS_LIST_NONE = re.compile(
    r"""\balgorithms\s*=\s*\[[^\]]*['"]\s*none\s*['"][^\]]*\]""",
    re.IGNORECASE,
)
RE_ALGS_NONE_VAL = re.compile(r"\balgorithms\s*=\s*None\b")

RE_SUPPRESS = re.compile(r"#\s*jwt-decode-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Mask out `#` comments and the *contents* of string literals
    (single + triple), preserving column positions and quote
    tokens. Triple-quote state is carried across lines."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def _matching_paren(s: str, open_idx: int) -> int:
    depth = 0
    for j in range(open_idx, len(s)):
        ch = s[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    # We need to inspect call args — possibly multi-line. To keep
    # the scanner single-pass and stdlib only, we look for an open
    # paren on the line where `decode(` matches and walk forward
    # until the balanced close paren, scrubbing each subsequent
    # line on the fly.
    lines = text.splitlines()
    scrubbed: list[str] = []
    cursor: str | None = None
    for raw in lines:
        s, cursor = strip_comments_and_strings(raw, cursor)
        scrubbed.append(s)

    for idx, scrub in enumerate(scrubbed):
        raw = lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_DECODE.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            # Walk forward to find balanced close paren.
            depth = 0
            j = idx
            collected: list[str] = []
            start_offset = paren
            while j < len(scrubbed):
                seg = scrubbed[j][start_offset:] if j == idx else scrubbed[j]
                for k, ch in enumerate(seg):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            collected.append(seg[: k + 1])
                            break
                else:
                    collected.append(seg)
                    j += 1
                    start_offset = 0
                    continue
                break
            args_text = "".join(collected)
            # Strip the leading "(" and trailing ")".
            inner = args_text[1:-1] if args_text.endswith(")") else args_text[1:]

            kinds: list[str] = []
            if RE_VERIFY_FALSE.search(inner):
                kinds.append("jwt-verify-false")
            if RE_VERIFY_SIG_FALSE.search(raw) or RE_VERIFY_SIG_FALSE.search(inner):
                # Note: literal contents are scrubbed in `inner`,
                # so we also probe the raw source line where the
                # decode call started for the options-dict pattern.
                kinds.append("jwt-verify-signature-false")
            if RE_ALG_SINGULAR_NONE.search(raw):
                kinds.append("jwt-algorithm-none")
            if RE_ALGS_LIST_NONE.search(raw):
                kinds.append("jwt-algorithms-list-none")
            if RE_ALGS_NONE_VAL.search(inner):
                kinds.append("jwt-algorithms-none-value")

            for kind in kinds:
                findings.append((path, idx + 1, m.start() + 1, kind, raw.strip()))
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
