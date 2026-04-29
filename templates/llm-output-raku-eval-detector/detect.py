#!/usr/bin/env python3
"""Detect Raku (Perl 6) string-EVAL anti-idioms.

Raku ships an `EVAL` routine and a `MONKEY-SEE-NO-EVAL` pragma that
together let any program turn a runtime string into executable Raku
code:

    use MONKEY-SEE-NO-EVAL;
    EVAL $user-input;

This is the Raku spelling of Python `exec(s)` or shell `eval $cmd`.
The MONKEY pragma exists precisely *because* the language designers
want every such call to be conspicuous — but LLM-emitted code is
happy to write the pragma at the top of the file and then forget
why it was conspicuous.

`EVAL` also has language-tagged forms:

    EVAL $s, :lang<Perl5>;
    EVAL $s, :lang<Raku>;
    use MONKEY;             # umbrella pragma that also enables EVAL

…and the legacy Perl 5-ish spellings `eval` / `evalfile` are still
recognised in Rakudo for porting compatibility, plus the
`Compiler.compile` reflective path:

    $*REPL.eval($s);
    $*W.compile($s);

Any of these, fed user-controlled or otherwise untrusted text, is
arbitrary-code execution inside the Raku runtime (full IO, full
shell, full FFI via `NativeCall`).

What this flags
---------------
* `EVAL <expr>`                 — bareword `EVAL` followed by a value
* `EVAL(<expr>)`                — call form
* `.EVAL`                       — method-call form on any expression
* `use MONKEY-SEE-NO-EVAL`      — the gating pragma itself (warn:
                                  presence is a strong signal that
                                  string-EVAL is in this file)
* `use MONKEY`                  — umbrella pragma, same warning
* `EVALFILE` / `evalfile`       — file-path EVAL
* `.compile($s)` on `$*W` /
   `$*REPL` / `Compiler`        — reflective compile-string path

Out of scope (deliberately)
---------------------------
* Perl 5 `eval { BLOCK }` style — that's exception trapping, not
  string-EVAL. We only flag `eval` when it has a non-block argument
  on the same expression.
* `EVAL` mentions inside `# ...` comments, `=begin pod ... =end pod`
  pod blocks, or string literals (`"..."`, `'...'`, `q[...]`, `Q[...]`)
  are masked out before scanning.

Suppression
-----------
Trailing `# eval-string-ok` comment on the same line suppresses that
finding — use sparingly and never on user-tainted input.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.raku, *.rakumod, *.rakudoc,
*.rakutest, *.p6, *.pm6, *.pl6, *.t6.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `EVAL` as a bareword call. We require the token to be at a word
# boundary, NOT preceded by a `:` (so `:EVAL` adverb-keys don't
# trigger) and NOT preceded by `-` (so `MONKEY-SEE-NO-EVAL` text
# isn't double-flagged here — the pragma rule handles it). The
# expression form may be `EVAL(...)`, `EVAL $x`, or `EVAL "..."`.
RE_EVAL_CALL = re.compile(
    r"(?<![A-Za-z0-9_:\-])EVAL\s*[\(\$\"\'qQ]"
)
# Method-call `.EVAL` on any expression
RE_DOT_EVAL = re.compile(
    r"\.\s*EVAL\b"
)
# EVALFILE — bareword or method form
RE_EVALFILE = re.compile(
    r"(?<![A-Za-z0-9_:\-])(?:EVALFILE|evalfile)\b"
)
# Pragmas that gate / enable string-EVAL
RE_MONKEY_PRAGMA = re.compile(
    r"^\s*use\s+(MONKEY-SEE-NO-EVAL|MONKEY)\b"
)
# Reflective compile-string: $*W.compile($s), $*REPL.eval($s),
# Compiler.new.compile($s).
RE_COMPILE_STRING = re.compile(
    r"(?:\$\*W|\$\*REPL|Compiler(?:\.new)?)\s*\.\s*(?:compile|eval)\s*\("
)
# Perl-5-ish lowercase `eval` followed by something that's NOT a
# block — i.e. `eval $x`, `eval "..."`, `eval(`. We require a
# non-`{` token after.
RE_LC_EVAL = re.compile(
    r"(?<![A-Za-z0-9_:\-])eval\s*[\(\$\"\']"
)

RE_SUPPRESS = re.compile(r"#\s*eval-string-ok\b")


def strip_comments_and_strings(text: str) -> str:
    """Mask out `#` line comments, `=begin pod ... =end pod` blocks,
    and the common Raku string literal forms: `"..."`, `'...'`,
    `q[...]`, `Q[...]`, `q{...}`, `Q{...}`, `q(...)`, `Q(...)`.

    Backslash escapes inside `"..."` are consumed. We do not try to
    handle every Q-language adverb spelling; the suppression comment
    is the safety valve.

    Operates line-by-line for `#` comments and quoted strings, with
    an outer pass to strip `=begin/=end` blocks. We do NOT try to
    track every Q-language adverb (`:to`, `:heredoc`, etc.) — the
    suppression comment is the safety valve.
    """
    # 1) strip pod blocks: `=begin pod` ... `=end pod` (or any name)
    out_lines: list[str] = []
    in_pod = False
    for raw in text.splitlines():
        s = raw.rstrip("\n")
        if not in_pod and re.match(r"^\s*=begin\s+\S+", s):
            in_pod = True
            out_lines.append("")
            continue
        if in_pod:
            out_lines.append("")
            if re.match(r"^\s*=end\s+\S+", s):
                in_pod = False
            continue
        out_lines.append(s)

    # 2) per-line mask of strings + `#` comments
    masked: list[str] = []
    for line in out_lines:
        out: list[str] = []
        i = 0
        n = len(line)
        in_dq = False  # "..."
        in_sq = False  # '...'
        in_q_paren = None  # one of ')', ']', '}' if inside q[...] / Q[...]
        while i < n:
            ch = line[i]
            if in_dq:
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == '"':
                    in_dq = False
                    out.append('"')
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            if in_sq:
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == "'":
                    in_sq = False
                    out.append("'")
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            if in_q_paren is not None:
                if ch == in_q_paren:
                    out.append(ch)
                    in_q_paren = None
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            # not currently inside any string
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
                out.append('"')
                i += 1
                continue
            if ch == "'":
                # Bare `'` is a string only if not part of an
                # identifier like `don't`. Raku allows `'` in
                # identifiers (e.g. `is'this`). Heuristic: treat as
                # string opener only if previous non-space char is
                # not an identifier char.
                prev = line[i - 1] if i > 0 else " "
                if prev.isalnum() or prev == "_":
                    out.append("'")
                    i += 1
                    continue
                in_sq = True
                out.append("'")
                i += 1
                continue
            # q[...] / Q[...] / q(...) / Q{...} / etc.
            if ch in "qQ" and i + 1 < n and line[i + 1] in "[({<":
                opener = line[i + 1]
                closer = {"[": "]", "(": ")", "{": "}", "<": ">"}[opener]
                out.append(ch)
                out.append(opener)
                in_q_paren = closer
                i += 2
                continue
            out.append(ch)
            i += 1
        masked.append("".join(out))
    return "\n".join(masked)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    raw_lines = text.splitlines()
    suppressed = {i + 1 for i, l in enumerate(raw_lines) if RE_SUPPRESS.search(l)}
    scrubbed = strip_comments_and_strings(text)
    scrubbed_lines = scrubbed.splitlines()

    line_starts = [0]
    for l in scrubbed_lines:
        line_starts.append(line_starts[-1] + len(l) + 1)

    def offset_to_linecol(off: int) -> tuple[int, int]:
        for ln, start in enumerate(line_starts):
            if start > off:
                return ln, off - line_starts[ln - 1] + 1
        return len(line_starts), off - line_starts[-1] + 1

    flat = "\n".join(scrubbed_lines)

    findings: list[tuple[int, int, str, str]] = []
    for kind, regex, multiline in (
        ("eval-call", RE_EVAL_CALL, False),
        ("dot-eval", RE_DOT_EVAL, False),
        ("evalfile", RE_EVALFILE, False),
        ("monkey-pragma", RE_MONKEY_PRAGMA, True),
        ("compile-string", RE_COMPILE_STRING, False),
        ("lowercase-eval-string", RE_LC_EVAL, False),
    ):
        if multiline:
            for ln, sl in enumerate(scrubbed_lines, 1):
                m = regex.search(sl)
                if not m or ln in suppressed:
                    continue
                snippet = raw_lines[ln - 1].strip() if 1 <= ln <= len(raw_lines) else ""
                findings.append((ln, m.start() + 1, kind, snippet))
        else:
            for m in regex.finditer(flat):
                line, col = offset_to_linecol(m.start())
                if line in suppressed:
                    continue
                snippet = raw_lines[line - 1].strip() if 1 <= line <= len(raw_lines) else ""
                findings.append((line, col, kind, snippet))
    findings.sort()
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    out: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line, col, kind, snippet in scan_text(text):
        out.append((path, line, col, kind, snippet))
    return out


def iter_targets(roots: list[str]):
    suffixes = {".raku", ".rakumod", ".rakudoc", ".rakutest",
                ".p6", ".pm6", ".pl6", ".t6"}
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in suffixes:
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
