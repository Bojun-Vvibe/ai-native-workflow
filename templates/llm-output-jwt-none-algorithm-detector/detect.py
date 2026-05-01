#!/usr/bin/env python3
"""Detect JWT verification code paths that accept the `none` algorithm.

The JWT spec allows an `alg: none` token whose signature is the
empty string. A verifier that does not pin an explicit algorithm
list — or worse, allows `"none"` in that list, or short-circuits
verification when the header says `none` — will accept any
forged token as authentic.

This shape shows up in LLM-emitted snippets across multiple
ecosystems:

* Python `jwt.decode(token, key, algorithms=[...])` where the
  `algorithms=` list is missing, empty, or includes `"none"`.
* Python `jwt.decode(...)` with `verify=False` or
  `options={"verify_signature": False}`.
* Node `jsonwebtoken.verify(token, key, { algorithms: [...] })`
  with `"none"` present, or `algorithms` missing entirely.
* Node `jwt.decode(token, ...)` used as if it verified (it does
  not — it only parses).
* Go `jwt.Parse` / `ParseWithClaims` whose keyfunc returns the key
  unconditionally for `*jwt.SigningMethodNone` / when the header
  alg is `"none"`.
* Hand-rolled "if header.alg == 'none' then accept" branches in
  any language.

What this does NOT flag
-----------------------
* `jwt.decode(token, key, algorithms=["HS256"])` etc. with a
  non-empty list that excludes `none`.
* Lines marked with a trailing `# jwt-none-ok` comment.
* Patterns inside `#` or `//` comment lines.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".cs", ".php"}

RE_SUPPRESS = re.compile(r"(?:#|//)\s*jwt-none-ok\b")
RE_PY_COMMENT = re.compile(r"^\s*#")
RE_JS_COMMENT = re.compile(r"^\s*//")

# Python: jwt.decode(...) — capture the call args until the matching ).
RE_PY_DECODE = re.compile(r"\bjwt\s*\.\s*decode\s*\(")
# Node: jsonwebtoken / jwt .verify(...) and .decode(...)
RE_JS_VERIFY = re.compile(r"\b(?:jwt|jsonwebtoken)\s*\.\s*verify\s*\(")
RE_JS_DECODE_AS_VERIFY = re.compile(r"\b(?:jwt|jsonwebtoken)\s*\.\s*decode\s*\(")

# Generic "alg(orithm)? == 'none'" branch
RE_NONE_BRANCH = re.compile(
    r"""(?ix)
    (?:alg(?:orithm)?)\s*
    (?:==|===|=|:|\.equals?\(|\.toLowerCase\(\)\s*==)\s*
    ['"]none['"]
    """
)

# Go: SigningMethodNone usage
RE_GO_NONE = re.compile(r"\bjwt\.SigningMethodNone\b|\bSigningMethodNone\b")

# Python verify=False / verify_signature False
RE_PY_VERIFY_FALSE = re.compile(r"verify\s*=\s*False\b")
RE_PY_VERIFY_SIG_FALSE = re.compile(
    r"""verify_signature['"]?\s*[:=]\s*False""", re.IGNORECASE
)


def find_call_span(text: str, start_paren: int):
    """Return (end_index_exclusive_of_close_paren, args_text) for the
    call whose '(' is at start_paren. Naive paren counter that
    respects single/double/backtick string literals and escapes.
    Returns (None, None) if not balanced within the file.
    """
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


def scan_python_decode_call(args: str) -> list[str]:
    issues = []
    # Look for explicit algorithms= kwarg
    m = re.search(r"algorithms\s*=\s*(\[[^\]]*\]|\([^)]*\)|None)", args)
    if m is None:
        # No algorithms kwarg at all → permissive
        issues.append("jwt-py-decode-missing-algorithms")
    else:
        body = m.group(1)
        if body.strip() == "None":
            issues.append("jwt-py-decode-algorithms-none")
        elif re.search(r"['\"]none['\"]", body, re.IGNORECASE):
            issues.append("jwt-py-decode-algorithms-includes-none")
        elif re.fullmatch(r"\[\s*\]|\(\s*\)", body.strip()):
            issues.append("jwt-py-decode-algorithms-empty")
    if RE_PY_VERIFY_FALSE.search(args):
        issues.append("jwt-py-decode-verify-false")
    if RE_PY_VERIFY_SIG_FALSE.search(args):
        issues.append("jwt-py-decode-verify-signature-false")
    return issues


def scan_js_verify_call(args: str) -> list[str]:
    issues = []
    m = re.search(r"algorithms\s*:\s*(\[[^\]]*\])", args)
    if m is None:
        issues.append("jwt-js-verify-missing-algorithms")
    else:
        body = m.group(1)
        if re.search(r"['\"]none['\"]", body, re.IGNORECASE):
            issues.append("jwt-js-verify-algorithms-includes-none")
        elif re.fullmatch(r"\[\s*\]", body.strip()):
            issues.append("jwt-js-verify-algorithms-empty")
    return issues


def scan_text(path: Path, text: str):
    findings = []
    suffix = path.suffix.lower()

    # 1. Python jwt.decode(...) calls
    if suffix == ".py":
        for m in RE_PY_DECODE.finditer(text):
            paren = m.end() - 1
            line = line_of(text, m.start())
            # Skip if suppressed on same line
            line_text = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
            if RE_SUPPRESS.search(line_text):
                continue
            if RE_PY_COMMENT.match(line_text):
                continue
            end, args = find_call_span(text, paren)
            if args is None:
                continue
            for kind in scan_python_decode_call(args):
                findings.append((path, line, 1, kind, line_text.strip()))

    # 2. Node jsonwebtoken.verify / .decode
    if suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        for m in RE_JS_VERIFY.finditer(text):
            paren = m.end() - 1
            line = line_of(text, m.start())
            line_text = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
            if RE_SUPPRESS.search(line_text):
                continue
            if RE_JS_COMMENT.match(line_text):
                continue
            end, args = find_call_span(text, paren)
            if args is None:
                continue
            for kind in scan_js_verify_call(args):
                findings.append((path, line, 1, kind, line_text.strip()))
        for m in RE_JS_DECODE_AS_VERIFY.finditer(text):
            line = line_of(text, m.start())
            line_text = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
            if RE_SUPPRESS.search(line_text):
                continue
            if RE_JS_COMMENT.match(line_text):
                continue
            # Heuristic: only flag if the call result is assigned to a var
            # named like 'verified' / 'authed' / 'payload' (used as auth).
            # Otherwise it is a legitimate header peek. We flag conservatively
            # only when followed within the same line by an obvious auth use.
            # To keep noise low, we only flag if the line also references
            # a verifying-sounding identifier.
            if re.search(r"\b(verified|authenticated|trusted|authPayload|isValid)\b", line_text):
                findings.append(
                    (path, line, 1, "jwt-js-decode-used-as-verify", line_text.strip())
                )

    # 3. Go: SigningMethodNone reference
    if suffix == ".go":
        for idx, raw in enumerate(text.splitlines(), start=1):
            if RE_SUPPRESS.search(raw):
                continue
            stripped = raw.lstrip()
            if stripped.startswith("//"):
                continue
            if RE_GO_NONE.search(raw):
                findings.append(
                    (path, idx, 1, "jwt-go-signing-method-none", raw.strip())
                )

    # 4. Generic alg == 'none' branch in any source file
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        stripped = raw.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if RE_NONE_BRANCH.search(raw):
            findings.append(
                (path, idx, 1, "jwt-alg-none-branch", raw.strip())
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
