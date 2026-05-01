#!/usr/bin/env python3
r"""Detect Express/Node code that reflects the request `Origin` header
back as `Access-Control-Allow-Origin` — typically combined with
`Access-Control-Allow-Credentials: true`.

Reflecting the request `Origin` is functionally equivalent to
`Access-Control-Allow-Origin: *`, except the spec actually allows
the browser to honour the response when credentials mode is
enabled. The result: any third-party site can make authenticated,
cookie-bearing requests to your API and read the response. This
is the canonical "permissive CORS" footgun and shows up
constantly in LLM-emitted Express middleware that is "trying to
make CORS work in dev".

What this flags
---------------
Node source files (`*.js`, `*.ts`, `*.mjs`, `*.cjs`, `*.jsx`,
`*.tsx`):

1. `cors({ origin: true, ... })` — the `cors` middleware's
   `origin: true` mode reflects the request Origin and is
   only safe when credentials are off.
   → `cors-pkg-origin-true`.
   If the same call also sets `credentials: true`, additionally
   reports `cors-pkg-origin-true-with-credentials` (high severity).

2. `cors({ origin: function(origin, cb){ cb(null, true) } })`
   shape — callback-based reflector that always returns the
   request origin as allowed.
   → `cors-pkg-origin-callback-always-true`.

3. Manual reflection via header set:
   `res.setHeader('Access-Control-Allow-Origin', req.headers.origin)`
   (and `res.header(...)` / `res.set(...)` variants).
   → `cors-manual-reflect-origin`.
   If the same file also sets `Access-Control-Allow-Credentials`
   to `true`, the reflection finding is upgraded to
   `cors-manual-reflect-origin-with-credentials`.

What this does NOT flag
-----------------------
* `cors({ origin: 'https://example.com' })` — explicit allowlist.
* `cors({ origin: ['https://a.example', 'https://b.example'] })`.
* `cors({ origin: /\.example\.com$/ })` — regex allowlist.
* `cors({ origin: false })` — disables CORS.
* Lines marked with a trailing `// cors-reflect-ok` comment.
* Patterns inside `//` line comments.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

RE_SUPPRESS = re.compile(r"//\s*cors-reflect-ok\b")
RE_LINE_COMMENT = re.compile(r"^\s*//")

# cors({ ... }) — find the call and grab the object literal.
RE_CORS_CALL = re.compile(r"\bcors\s*\(")

# Manual reflection: setHeader / header / set with ACAO header and
# req.headers.origin (or req.get('origin') / req.header('origin')).
RE_MANUAL_REFLECT = re.compile(
    r"""(?ix)
    \b(?:res|response|ctx\.res|ctx\.response)
    \s*\.\s*
    (?:setHeader|header|set)
    \s*\(\s*
    ['"]Access-Control-Allow-Origin['"]
    \s*,\s*
    (?:
        req(?:uest)?\s*\.\s*headers\s*\.\s*origin
      | req(?:uest)?\s*\.\s*headers\s*\[\s*['"]origin['"]\s*\]
      | req(?:uest)?\s*\.\s*get\s*\(\s*['"]origin['"]\s*\)
      | req(?:uest)?\s*\.\s*header\s*\(\s*['"]origin['"]\s*\)
      | ctx\s*\.\s*request\s*\.\s*headers?\s*\.\s*origin
      | origin
    )
    \s*\)
    """
)

# ACAC: true (in any header form)
RE_ACAC_TRUE = re.compile(
    r"""(?ix)
    ['"]Access-Control-Allow-Credentials['"]\s*,\s*['"]?true['"]?
    """
)

# In a cors({...}) options literal:
#   origin: true
RE_OPT_ORIGIN_TRUE = re.compile(r"\borigin\s*:\s*true\b")
#   credentials: true
RE_OPT_CRED_TRUE = re.compile(r"\bcredentials\s*:\s*true\b")
#   origin: function(origin, cb) { ... cb(null, true) ... }   (or arrow)
RE_OPT_ORIGIN_FN = re.compile(r"\borigin\s*:\s*(?:function\b|\([^)]*\)\s*=>|async\s+function\b)")
RE_CB_NULL_TRUE = re.compile(r"\b(?:cb|callback|done|next)\s*\(\s*null\s*,\s*true\s*\)")
# Arrow returning true directly: origin: (origin) => true
RE_ARROW_RETURN_TRUE = re.compile(r"\borigin\s*:\s*\([^)]*\)\s*=>\s*true\b")


def find_call_span(text: str, start_paren: int):
    """Balance parens starting at start_paren; respect string literals."""
    depth = 0
    i = start_paren
    n = len(text)
    in_str = None
    esc = False
    args_start = start_paren + 1
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i, text[args_start:i]
        i += 1
    return None, None


def line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def scan_text(path: Path, text: str):
    findings = []
    lines = text.splitlines()
    file_has_acac_true = bool(RE_ACAC_TRUE.search(text))

    # 1. cors({...}) calls
    for m in RE_CORS_CALL.finditer(text):
        paren = m.end() - 1
        line = line_of(text, m.start())
        line_text = lines[line - 1] if line - 1 < len(lines) else ""
        if RE_SUPPRESS.search(line_text):
            continue
        if RE_LINE_COMMENT.match(line_text):
            continue
        end, args = find_call_span(text, paren)
        if args is None:
            continue
        # Strip nested string content for safer pattern matching by
        # operating on the raw args text (the regexes above are tight).
        cred_true = bool(RE_OPT_CRED_TRUE.search(args))
        origin_true = bool(RE_OPT_ORIGIN_TRUE.search(args))
        origin_fn = bool(RE_OPT_ORIGIN_FN.search(args))
        arrow_true = bool(RE_ARROW_RETURN_TRUE.search(args))
        cb_null_true = bool(RE_CB_NULL_TRUE.search(args))
        if origin_true:
            if cred_true:
                findings.append(
                    (path, line, 1,
                     "cors-pkg-origin-true-with-credentials",
                     line_text.strip())
                )
            else:
                findings.append(
                    (path, line, 1, "cors-pkg-origin-true", line_text.strip())
                )
        if arrow_true or (origin_fn and cb_null_true):
            findings.append(
                (path, line, 1,
                 "cors-pkg-origin-callback-always-true",
                 line_text.strip())
            )

    # 2. Manual reflection
    for m in RE_MANUAL_REFLECT.finditer(text):
        line = line_of(text, m.start())
        line_text = lines[line - 1] if line - 1 < len(lines) else ""
        if RE_SUPPRESS.search(line_text):
            continue
        if RE_LINE_COMMENT.match(line_text):
            continue
        if file_has_acac_true:
            findings.append(
                (path, line, 1,
                 "cors-manual-reflect-origin-with-credentials",
                 line_text.strip())
            )
        else:
            findings.append(
                (path, line, 1, "cors-manual-reflect-origin", line_text.strip())
            )

    return findings


def iter_targets(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SUFFIXES:
                    yield sub
        elif p.is_file():
            yield p


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for f_path, line, col, kind, snippet in scan_text(path, text):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
