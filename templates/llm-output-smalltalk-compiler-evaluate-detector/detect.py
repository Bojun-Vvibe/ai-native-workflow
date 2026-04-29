#!/usr/bin/env python3
"""Detect Smalltalk runtime string-evaluation anti-idioms.

Smalltalk dialects (Pharo, Squeak, GNU Smalltalk, VisualWorks,
Cuis, Dolphin) all expose first-class metacircular evaluators.
The canonical spellings for "compile and run an arbitrary string
right now" are:

    Compiler evaluate: aString
    Compiler evaluate: aString for: anObject
    Compiler evaluate: aString for: anObject logged: false

    OpalCompiler new evaluate: aString
    OpalCompiler new source: aString; evaluate
    Smalltalk compiler evaluate: aString.
    Smalltalk compileString: aString.

    aString evaluate
    aString asExpression
    Object evaluate: aString

…plus the parser/AST entry points that get composed into the same
pipeline:

    RBParser parseExpression: aString
    Parser new parse: aString class: UndefinedObject
    SmaCCParser parse: aString

Any of these, fed user-controlled or otherwise untrusted text, is
arbitrary-code execution inside the image — full filesystem, full
sockets, full reflection, full image surgery.

What this flags
---------------
* `Compiler evaluate:` (with optional `for:` / `logged:` /
  `notifying:` continuations)
* `OpalCompiler ... evaluate` (any keyword chain that ends in
  `evaluate` after an `OpalCompiler` receiver)
* `Smalltalk compiler evaluate:` and `Smalltalk compileString:`
* Bare `<receiver> evaluate` and `<receiver> evaluate:` on a
  string-typed receiver (heuristic: line contains a single-quoted
  string literal AND ends with `evaluate` / `evaluate:`)
* `<receiver> asExpression` (Pharo idiom)
* `RBParser parseExpression:`, `Parser new parse:`,
  `SmaCCParser parse:`
* `ClassBuilder ... compile:` runtime class-extension path

Out of scope (deliberately)
---------------------------
* `Compiler` referenced as a *class symbol* with no `evaluate`
  message — that's reflection, not eval.
* Mentions inside `"..."` (Smalltalk uses double-quotes for
  comments) and inside `'...'` string literals are masked out
  before scanning.

Suppression
-----------
Trailing `"eval-string-ok"` comment on the same line suppresses
that finding — the scanner looks for the literal token
`eval-string-ok` inside any masked comment region on the line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.st, *.cs (Cincom file-out)
and *.changes. (`.cs` is also a C# extension; if that's a problem
in your repo, pass individual files.)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_COMPILER_EVALUATE = re.compile(
    r"\bCompiler\s+evaluate:"
)
RE_OPAL_COMPILER = re.compile(
    r"\bOpalCompiler\b[^.]*?\bevaluate\b"
)
RE_SMALLTALK_COMPILER = re.compile(
    r"\bSmalltalk\s+compiler\s+evaluate:"
)
RE_SMALLTALK_COMPILESTRING = re.compile(
    r"\bSmalltalk\s+compileString:"
)
RE_AS_EXPRESSION = re.compile(
    r"\basExpression\b"
)
RE_RBPARSER = re.compile(
    r"\bRBParser\s+parseExpression:"
)
RE_PARSER_NEW_PARSE = re.compile(
    r"\bParser\s+new\s+parse:"
)
RE_SMACCPARSER = re.compile(
    r"\bSmaCCParser\s+parse:"
)
RE_CLASSBUILDER_COMPILE = re.compile(
    r"\bClassBuilder\b[^.]*?\bcompile:"
)
# Heuristic: a line that has a `'...'` string literal AND ends in
# (or contains) `evaluate` / `evaluate:` — likely string-eval.
RE_TRAILING_EVALUATE = re.compile(
    r"\bevaluate(?::|\s|\.|;|$)"
)
RE_HAS_STRING_LITERAL = re.compile(
    r"'[^'\n]*'"
)

RE_SUPPRESS = re.compile(r"eval-string-ok\b")


def strip_comments_and_strings(text: str) -> str:
    """Mask `"..."` Smalltalk comments and `'...'` string literals.

    Smalltalk uses `''` (doubled apostrophe) to escape an apostrophe
    inside a literal. We treat `''` as an escape sequence and stay
    inside the literal.
    """
    masked: list[str] = []
    in_dq = False  # "..." comment — spans lines in Smalltalk
    in_sq = False  # '...' string literal — also spans lines
    for line in text.splitlines():
        out: list[str] = []
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if in_dq:
                if ch == '"':
                    in_dq = False
                    out.append('"')
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            if in_sq:
                if ch == "'":
                    if i + 1 < n and line[i + 1] == "'":
                        # escaped quote — stay in string
                        out.append("  ")
                        i += 2
                        continue
                    in_sq = False
                    out.append("'")
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            if ch == '"':
                in_dq = True
                out.append('"')
                i += 1
                continue
            if ch == "'":
                in_sq = True
                out.append("'")
                i += 1
                continue
            out.append(ch)
            i += 1
        masked.append("".join(out))
    return "\n".join(masked)


KINDS_DIRECT = (
    ("compiler-evaluate", RE_COMPILER_EVALUATE),
    ("opal-compiler", RE_OPAL_COMPILER),
    ("smalltalk-compiler", RE_SMALLTALK_COMPILER),
    ("smalltalk-compilestring", RE_SMALLTALK_COMPILESTRING),
    ("as-expression", RE_AS_EXPRESSION),
    ("rbparser-expr", RE_RBPARSER),
    ("parser-new-parse", RE_PARSER_NEW_PARSE),
    ("smaccparser-parse", RE_SMACCPARSER),
    ("classbuilder-compile", RE_CLASSBUILDER_COMPILE),
)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    raw_lines = text.splitlines()
    # Suppression keys off the *raw* line so that `"eval-string-ok"`
    # inside a Smalltalk comment is honored.
    suppressed = {i + 1 for i, l in enumerate(raw_lines) if RE_SUPPRESS.search(l)}
    scrubbed_lines = strip_comments_and_strings(text).splitlines()

    findings: list[tuple[int, int, str, str]] = []
    for ln, sl in enumerate(scrubbed_lines, 1):
        if ln in suppressed:
            continue
        raw = raw_lines[ln - 1] if 1 <= ln <= len(raw_lines) else ""
        snippet = raw.strip()
        for kind, regex in KINDS_DIRECT:
            for m in regex.finditer(sl):
                findings.append((ln, m.start() + 1, kind, snippet))
        # Heuristic: string literal + bare `evaluate` on the same
        # line. Use the *raw* line for the string-literal check
        # (because masking erased the literal in `sl`) and the
        # scrubbed line for the `evaluate` check (so `evaluate`
        # mentioned inside a comment doesn't trigger).
        if RE_HAS_STRING_LITERAL.search(raw) and RE_TRAILING_EVALUATE.search(sl):
            # avoid double-firing if `compiler-evaluate` etc.
            # already matched on this line
            already = {f for f in findings if f[0] == ln}
            if not already:
                m = RE_TRAILING_EVALUATE.search(sl)
                findings.append((ln, m.start() + 1, "string-evaluate", snippet))
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
    suffixes = {".st", ".cs", ".changes"}
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
