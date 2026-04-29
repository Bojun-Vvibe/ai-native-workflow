#!/usr/bin/env python3
"""Detect shell-escape sinks in TeX / LaTeX source.

See README.md for rationale and rules. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"%\s*tex-exec-ok\b")

# Primitive call followed by a `{...}` group. We extract the group
# greedily on the same scrubbed line; for cross-line groups we fall
# back to "treat the rest of the line as the argument span".
RE_WRITE18 = re.compile(r"\\(?:immediate\s*\\)?write18\s*\{([^{}]*)\}")
RE_WRITE18_OPEN = re.compile(r"\\(?:immediate\s*\\)?write18\s*\{")
RE_DIRECTLUA = re.compile(r"\\directlua\s*\{([^{}]*)\}")
RE_DIRECTLUA_OPEN = re.compile(r"\\directlua\s*\{")
RE_SHELLESCAPE = re.compile(r"\\ShellEscape\s*\{([^{}]*)\}")
RE_SHELLESCAPE_OPEN = re.compile(r"\\ShellEscape\s*\{")
# \input|"cmd"  or  \input|'cmd'
RE_INPUT_PIPE = re.compile(r"\\input\s*\|\s*([\"'])(.*?)\1")

RE_MACRO_REF = re.compile(r"\\[A-Za-z@]+")


def strip_comments_and_strings(line: str) -> str:
    """Blank `% ...EOL` comments (honoring `\\%` as a literal). We do
    NOT blank curly groups here -- callers that want to inspect a
    group's *contents* (rather than the command spelling) handle the
    string-literal blanking themselves."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n and line[i + 1] == "%":
            out.append("\\%")
            i += 2
            continue
        if ch == "%":
            out.append(" " * (n - i))
            break
        out.append(ch)
        i += 1
    return "".join(out)


def blank_string_literals(s: str) -> str:
    """Blank the *contents* of "..." and '...' string literals. Used
    to decide whether the surviving span still has macro refs."""
    out: list[str] = []
    i = 0
    n = len(s)
    quote = ""
    while i < n:
        ch = s[i]
        if quote:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                out.append(ch)
                quote = ""
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_dynamic(arg: str) -> bool:
    """True if, after blanking string contents, the argument still
    contains a `\\macro` reference. Bare command literals stay pure
    text and are *not* dynamic."""
    blanked = blank_string_literals(arg)
    return RE_MACRO_REF.search(blanked) is not None


def is_tex_file(path: Path) -> bool:
    return path.suffix in (".tex", ".ltx", ".sty", ".cls", ".dtx")


def _emit_inline(
    findings: list, path: Path, line_no: int, raw: str, scrub: str,
    pat_full: re.Pattern, pat_open: re.Pattern, base_kind: str,
) -> None:
    matched = False
    for m in pat_full.finditer(scrub):
        matched = True
        arg = m.group(1)
        kind = f"{base_kind}-dynamic" if is_dynamic(arg) else base_kind
        findings.append((path, line_no, m.start() + 1, kind, raw.strip()))
    if matched:
        return
    # Fallback: opening primitive but the `}` is on a later line.
    m2 = pat_open.search(scrub)
    if m2:
        tail = scrub[m2.end():]
        kind = f"{base_kind}-dynamic" if is_dynamic(tail) else base_kind
        findings.append((path, line_no, m2.start() + 1, kind, raw.strip()))


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)

        _emit_inline(findings, path, idx, raw, scrub,
                     RE_WRITE18, RE_WRITE18_OPEN, "tex-write18")
        _emit_inline(findings, path, idx, raw, scrub,
                     RE_SHELLESCAPE, RE_SHELLESCAPE_OPEN, "tex-shellescape")

        # \directlua: only flag when its body uses os.execute / io.popen
        for m in RE_DIRECTLUA.finditer(scrub):
            body = m.group(1)
            if "os.execute" in body:
                kind = "tex-directlua-execute"
            elif "io.popen" in body:
                kind = "tex-directlua-popen"
            else:
                continue
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        # Multi-line directlua: be conservative and flag the opener if
        # we see suspicious tokens later on the same line.
        if not RE_DIRECTLUA.search(scrub):
            m2 = RE_DIRECTLUA_OPEN.search(scrub)
            if m2:
                tail = scrub[m2.end():]
                if "os.execute" in tail:
                    findings.append((path, idx, m2.start() + 1,
                                     "tex-directlua-execute", raw.strip()))
                elif "io.popen" in tail:
                    findings.append((path, idx, m2.start() + 1,
                                     "tex-directlua-popen", raw.strip()))

        for m in RE_INPUT_PIPE.finditer(scrub):
            cmd = m.group(2)
            kind = "tex-input-pipe-dynamic" if is_dynamic(cmd) else "tex-input-pipe"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_tex_file(sub):
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
