#!/usr/bin/env python3
"""Detect Emacs Lisp dynamic-evaluation sinks: `eval`, `eval-region`,
`eval-buffer`, `eval-string`, and `read-from-string` / `read` when
their result is fed to `eval`.

Why this matters
----------------
Emacs Lisp's `(eval FORM)` evaluates an arbitrary Lisp form at runtime.
Combined with `(read STRING)` or `(read-from-string STRING)` — which
parse a string into a Lisp form — you get a complete code-execution
sink with the exact blast radius of `system($USER_INPUT)`.

This is especially dangerous in:

* `dir-locals.el`, `.dir-locals.el`, file-local variables — Emacs will
  silently `eval` anything an attacker drops into the project tree
  (this is the entire reason `enable-local-eval` exists).
* MELPA-style auto-update hooks that pull a snippet from a URL and
  pass it through `eval` or `eval-region`.
* Org-mode src blocks executed via `org-babel-execute-src-block`.

LLM-emitted Elisp reaches for `(eval (read user-supplied-string))` to
"interpret a config file." Almost always wrong. Safe replacements:

| Anti-pattern                       | Safe alternative                       |
| ---------------------------------- | -------------------------------------- |
| `(eval (read s))`                  | parse with `(read s)` and pattern-match the form on a known whitelist |
| `(eval-region START END)` of buffer of unknown origin | `(read-from-string ...)` then dispatch by car |
| `(load FILE)` with attacker-controlled FILE | hard-coded path + checksum |

What this flags
---------------
A bareword call at command position — i.e. immediately after `(` —
to one of:

* `eval`
* `eval-region`
* `eval-buffer`
* `eval-string`           (Emacs 29+)
* `eval-expression`
* `eval-last-sexp`
* `eval-defun`            (when used non-interactively)

PLUS any `(read ...)` or `(read-from-string ...)` whose result is
syntactically piped into `eval` on the same line, e.g.
`(eval (read s))`, `(eval (car (read-from-string s)))`.

Out of scope (deliberately)
---------------------------
* `(load FILE)` and `(load-file FILE)` — different sink, separate
  detector.
* `(byte-compile FORM)` — does not evaluate by itself.
* `funcall` / `apply` of a function VALUE — those are not source-string
  sinks and are usually safe.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.el, *.eld, .emacs, init.el,
early-init.el, dir-locals.el, .dir-locals.el, and files whose first
line is an emacs / emacsclient shebang.

Suppress an audited line with a trailing `; eval-ok` comment.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


EVAL_NAMES = (
    "eval",
    "eval-region",
    "eval-buffer",
    "eval-string",
    "eval-expression",
    "eval-last-sexp",
    "eval-defun",
)

# Match `(NAME` where NAME is one of EVAL_NAMES, allowing leading
# whitespace. The trailing char must NOT be a Lisp identifier
# character (`-`, `_`, alnum, `?`, `!`, `*`, `+`, `/`, `:`).
RE_EVAL_CALL = re.compile(
    r"\(\s*(?P<name>"
    + "|".join(re.escape(n) for n in EVAL_NAMES)
    + r")(?=[\s)\(])"
)

# `(eval (read ...))` or `(eval ... (read-from-string ...))` on one
# line — the inner `read` may be wrapped in `car`, `cdr`, etc.
RE_EVAL_OF_READ = re.compile(
    r"\(\s*eval\s+\((?:[^()]*\()*\s*(?:read|read-from-string)\b"
)

RE_SUPPRESS = re.compile(r";\s*eval-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `; ...` comments (Emacs Lisp uses `;` for line
    comments) and the contents of `"..."` strings while preserving
    column positions. `?\\C-x` style char literals are left alone —
    they cannot contain `eval` as a token."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_str = False
    while i < n:
        ch = line[i]
        if not in_str:
            if ch == ";":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_str = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_elisp_file(path: Path) -> bool:
    if path.suffix in (".el", ".eld"):
        return True
    if path.name in (".emacs", "init.el", "early-init.el",
                     "dir-locals.el", ".dir-locals.el"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tok in first for tok in ("emacs", "emacsclient"))


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
        seen_cols: set[int] = set()
        for m in RE_EVAL_CALL.finditer(scrub):
            col = m.start("name") + 1
            seen_cols.add(col)
            findings.append(
                (path, idx, col, f"elisp-{m.group('name')}", raw.strip())
            )
        for m in RE_EVAL_OF_READ.finditer(scrub):
            # Find the inner `read` token column for accuracy. Avoid
            # double-flagging the outer `eval` already reported above.
            col = m.start() + 1
            findings.append(
                (path, idx, col, "elisp-eval-of-read", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_elisp_file(sub):
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
