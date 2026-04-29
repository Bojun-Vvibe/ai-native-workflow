#!/usr/bin/env python3
"""Detect dangerous Haskell `hint`-package runtime-eval calls.

The `hint` package (Language.Haskell.Interpreter) exposes:

    eval        :: String -> Interpreter String
    interpret   :: String -> a -> Interpreter a
    runStmt     :: String -> Interpreter ()

When the String argument is non-literal (a variable, a function
application, a `<>` / `++` concatenation involving a non-literal,
etc.), an attacker who controls that value gets arbitrary Haskell
execution.

What this flags
---------------
* `eval x` where `x` is not a string literal
* `interpret expr (as :: T)` where `expr` is not a string literal
* `runStmt s` where `s` is not a string literal
* `eval ("prefix" ++ x)` and similar concatenations
* qualified forms: `Hint.eval x`, `H.interpret x ty`,
  `Language.Haskell.Interpreter.eval x`

What this does NOT flag
-----------------------
* `eval "1 + 1"`             — fully literal
* `interpret "show 42" (as :: String)`
* `runStmt "putStrLn \"hi\""`
* the unrelated `Prelude.read` (different sink, different family)
* `Data.Map.eval` and any other identifier merely *named* `eval`
  that does not appear at a call position with a non-literal arg

Suppression
-----------
Trailing `-- hint-ok` on the same line.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses looking for *.hs and *.lhs files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Sink token at a call position, optionally qualified
# (Foo.Bar.eval). We match the unqualified function name preceded
# by either start-of-line, a non-identifier character, or a `.` from
# a module qualifier. We then require what follows to be a function
# argument (whitespace + non-`=`/`<-`).
SINK_NAMES = ("eval", "interpret", "runStmt")
RE_SINK = re.compile(
    r"(?:^|(?<=[\s(,$;{|]))"
    r"(?:[A-Z][\w']*(?:\.[A-Z][\w']*)*\.)?"
    r"(eval|interpret|runStmt)\b"
    r"(?P<rest>[^\n]*)"
)

RE_SUPPRESS = re.compile(r"--\s*hint-ok\b")

# A Haskell string literal. Allow simple `\"` escapes.
RE_STRING_LIT = re.compile(r'"(?:\\.|[^"\\])*"')


def strip_comments_and_strings(line: str, in_block: bool) -> tuple[str, bool]:
    """Blank `--` line comments, `{- ... -}` block comments (carrying
    state across lines), and the *contents* of double-quoted strings
    (Haskell has no other string literal that could carry an
    expression). Column positions preserved.

    Returns the scrubbed line and the new in-block-comment state.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    while i < n:
        ch = line[i]
        if in_block:
            if ch == "-" and i + 1 < n and line[i + 1] == "}":
                out.append("  ")
                i += 2
                in_block = False
                continue
            out.append(" ")
            i += 1
            continue
        if in_dq:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_dq = False
                out.append(ch)
                i += 1
                continue
            # Blank string contents so a literal that contains the
            # word "eval" does not trip us.
            out.append(" ")
            i += 1
            continue
        # Not in any quote/comment.
        if ch == "{" and i + 1 < n and line[i + 1] == "-":
            out.append("  ")
            i += 2
            in_block = True
            continue
        if ch == "-" and i + 1 < n and line[i + 1] == "-":
            # Line comment to EOL.
            out.append(" " * (n - i))
            break
        if ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), in_block


def first_arg_is_pure_literal(rest_scrubbed: str, rest_raw: str) -> bool:
    """Decide whether the first argument of a sink call is a single,
    fully-literal Haskell string (and nothing else combined with it).

    `rest_scrubbed` has string contents blanked but the surrounding
    `"` quotes preserved. `rest_raw` is the original line tail.

    Heuristic: skip leading whitespace; if the next char is `"`, find
    the matching closing `"` in the RAW text (so escapes are honored)
    and confirm that what follows in the SCRUBBED text up to a
    boundary character is whitespace followed by argument terminators
    only (end-of-line, `--` comment, `)`, `,`, `$`, type ascription
    `::`, `where`, `do`, etc. — broadly: NOT another infix operator
    like `++` or `<>`).
    """
    j = 0
    while j < len(rest_scrubbed) and rest_scrubbed[j] in " \t":
        j += 1
    if j >= len(rest_scrubbed) or rest_scrubbed[j] != '"':
        return False
    # Find matching closing quote in raw text starting at the same
    # offset (rest_raw and rest_scrubbed are aligned).
    k = j + 1
    while k < len(rest_raw):
        c = rest_raw[k]
        if c == "\\" and k + 1 < len(rest_raw):
            k += 2
            continue
        if c == '"':
            break
        k += 1
    if k >= len(rest_raw):
        return False
    # After the closing quote, look at the scrubbed remainder.
    tail = rest_scrubbed[k + 1 :]
    # Strip trailing line-comment content (already blanked) and
    # whitespace.
    tail_stripped = tail.rstrip()
    if not tail_stripped:
        return True
    # Allow a type ascription, an additional non-string literal-ish
    # second argument used by `interpret`, a closing paren, comma,
    # `$`, `>>=`, `>>`, `do`, `where`, `in`. Any of those means the
    # FIRST arg is still literal.
    # Disallow `++`, `<>`, `<<>>`, `mappend` — those compose another
    # piece into the eval'd string.
    if re.match(
        r"^\s*(?:::|\)|,|\$|>>=|>>|do\b|where\b|in\b|"
        r"\(\s*as\s*::|--)",
        tail_stripped,
    ):
        return True
    # If the next non-whitespace token is another argument that is
    # itself pure (e.g. `(as :: IO ())`), accept.
    if tail_stripped.startswith("("):
        return True
    # Otherwise we conservatively say: not pure literal.
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    # Gate: only scan files that import the hint runtime-eval module.
    # An import like `import Language.Haskell.Interpreter` (qualified
    # or otherwise) is required for these sinks to mean what we
    # think they mean. Files without it might use the names for
    # unrelated local functions or record fields.
    if not re.search(r"^\s*import\s+(?:qualified\s+)?Language\.Haskell\.Interpreter\b", text, re.M):
        return findings
    in_block = False
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            # Still need to advance block-comment state.
            scrub, in_block = strip_comments_and_strings(raw, in_block)
            continue
        scrub, in_block = strip_comments_and_strings(raw, in_block)
        for m in RE_SINK.finditer(scrub):
            sink = m.group(1)
            rest_scrubbed = m.group("rest")
            rest_start = m.start("rest")
            rest_raw = raw[rest_start:rest_start + len(rest_scrubbed)]
            # Must look like a function call: at least one space (or
            # `(`) before the next token, otherwise it's part of a
            # longer identifier — already prevented by `\b` — or it
            # is `eval=...` (assignment in a record). Reject `=`/`<-`
            # right after the name.
            stripped_lead = rest_scrubbed.lstrip()
            if stripped_lead.startswith(("=", "<-", "::", "->")):
                continue
            # Must have an actual argument on the same line.
            if not stripped_lead:
                continue
            if first_arg_is_pure_literal(rest_scrubbed, rest_raw):
                continue
            col = m.start(1) + 1
            kind = f"haskell-hint-{sink}-dynamic"
            findings.append((path, idx, col, kind, raw.strip()))
    return findings


def is_haskell_file(path: Path) -> bool:
    return path.suffix in (".hs", ".lhs")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_haskell_file(sub):
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
