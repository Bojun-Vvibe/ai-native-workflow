#!/usr/bin/env python3
"""
llm-output-nodejs-jwt-no-algorithm-pin-detector

Flags Node.js source that calls `jwt.verify(...)` (or
`jsonwebtoken.verify(...)`) without pinning the `algorithms:` allowlist
in the options bag. Maps to **CWE-327: Use of a Broken or Risky
Cryptographic Algorithm** and the well-known "alg confusion" family
(CVE-2015-9235 / CVE-2016-10555 and friends): when the verifier does
not constrain accepted algorithms, an attacker who knows the public
RSA key can sign a token using HS256 with that public key as the HMAC
secret, and the library will happily accept it as valid.

This is distinct from:
  - `llm-output-jwt-none-alg-detector` (which flags signing with `alg=none`)
  - `llm-output-python-jwt-no-verify-detector` (which flags Python `verify=False`)

We focus specifically on the Node.js `jsonwebtoken` API surface: the
mitigation upstream's own README recommends is *always pass an
algorithms allowlist* to `verify()`. LLM-generated samples routinely
omit it because the function still "works" with no third argument.

Stdlib-only Python. Reads files passed on argv (or recurses into dirs
and picks `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.tsx`).
Exit 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
1. For each source file, walk lines and find call sites of the form
   `<id>.verify(` where `<id>` is `jwt`, `jsonwebtoken`, `JWT`, or any
   identifier we have seen `require('jsonwebtoken')` / `import ... from
   'jsonwebtoken'` bound to in the same file.
2. Capture the parenthesized argument list, balancing parens across
   newlines (we cap at 40 lines to avoid runaway).
3. If the call site does not contain an `algorithms:` (or `algorithms =`)
   key anywhere in its arguments, emit a finding.
4. We also flag the explicit `algorithms: ['none']` case because that
   is just the alg-confusion shortcut.

We deliberately do not try to type-check the options object; if the
options bag is hoisted to a const above the call, we *do* try to find
a sibling `const opts = { algorithms: [...] }` declaration and accept
it. Anything more sophisticated than that is out of scope.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Set

_REQUIRE_RE = re.compile(
    r"""(?:const|let|var)\s+(?P<id>[A-Za-z_$][\w$]*)\s*=\s*"""
    r"""require\(\s*['"]jsonwebtoken['"]\s*\)""",
)
_IMPORT_RE = re.compile(
    r"""import\s+(?:(?P<def>[A-Za-z_$][\w$]*)|\*\s*as\s+(?P<star>[A-Za-z_$][\w$]*)|"""
    r"""\{[^}]*\})\s+from\s+['"]jsonwebtoken['"]""",
)
# Catches `import { verify as jwtVerify } from 'jsonwebtoken'`
_IMPORT_NAMED_VERIFY = re.compile(
    r"""import\s*\{\s*[^}]*\bverify(?:\s+as\s+(?P<alias>[A-Za-z_$][\w$]*))?[^}]*\}\s*from\s*['"]jsonwebtoken['"]""",
)

# Match a verify call: <id>.verify(   OR   verify(   if bound directly.
def _verify_call_re(ids: Set[str]) -> re.Pattern:
    members = "|".join(sorted({re.escape(i) for i in ids if i})) or "jwt"
    pattern = (
        r"(?P<who>(?:" + members + r")\s*\.\s*verify|\bverify)\s*\("
    )
    return re.compile(pattern)


# Detect a hoisted options object: `const opts = { ... algorithms: ... }`
_OPTS_DECL_RE = re.compile(
    r"""(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*\{(?P<body>[^{}]*algorithms\s*:[^{}]*)\}""",
    re.DOTALL,
)


def _balanced_args(text: str, open_idx: int, max_lines: int = 40) -> str:
    """Return the substring of `text` containing the balanced argument
    list starting at `open_idx` (which must point at the `(`).
    Stops after `max_lines` of newline traversal. If unbalanced,
    returns whatever was scanned."""
    depth = 0
    out_chars = []
    nl = 0
    for ch in text[open_idx:]:
        if ch == "\n":
            nl += 1
            if nl > max_lines:
                break
        out_chars.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    return "".join(out_chars)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # Build identifier set bound to jsonwebtoken in this file.
    ids: Set[str] = set()
    for m in _REQUIRE_RE.finditer(text):
        ids.add(m.group("id"))
    for m in _IMPORT_RE.finditer(text):
        if m.group("def"):
            ids.add(m.group("def"))
        if m.group("star"):
            ids.add(m.group("star"))
    direct_verify_alias = None
    for m in _IMPORT_NAMED_VERIFY.finditer(text):
        direct_verify_alias = m.group("alias") or "verify"
    # Always include the conventional names so we still flag
    # `jwt.verify(...)` even when the require/import lives in another file.
    ids.update({"jwt", "jsonwebtoken", "JWT"})

    # Pre-collect any hoisted options decls that pin algorithms.
    safe_opts_names: Set[str] = set()
    for m in _OPTS_DECL_RE.finditer(text):
        safe_opts_names.add(m.group("name"))

    # Compute line offsets for line-number reporting.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def lineno_for(offset: int) -> int:
        # Binary search would be nicer, but files are small.
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    pattern = _verify_call_re(ids)
    # Also handle the named-import alias (e.g. `verify as jwtVerify`)
    if direct_verify_alias and direct_verify_alias != "verify":
        pattern = re.compile(
            pattern.pattern + r"|\b" + re.escape(direct_verify_alias) + r"\s*\("
        )

    for m in pattern.finditer(text):
        # Find the `(` that starts the args.
        open_idx = text.find("(", m.start())
        if open_idx == -1:
            continue
        args = _balanced_args(text, open_idx)
        # Skip declarations like `function verify(...)` or method defs.
        # We only want call sites, so require there is no `function ` or
        # `class ` keyword immediately before the match.
        prelude = text[max(0, m.start() - 12) : m.start()]
        if re.search(r"\bfunction\s*$|\bclass\s+\w+\s*$", prelude):
            continue

        # If the args mention `algorithms:` or `algorithms =`, accept --
        # unless the value is the literal `['none']` / `["none"]`.
        none_only = re.search(
            r"algorithms\s*[:=]\s*\[\s*['\"]none['\"]\s*\]",
            args,
            re.IGNORECASE,
        )
        if none_only:
            findings.append(
                f"{path}:{lineno_for(m.start())}: jsonwebtoken.verify "
                f"with algorithms: ['none'] (CWE-327, alg-confusion enabler)"
            )
            continue
        if re.search(r"\balgorithms\s*[:=]", args):
            continue

        # If args reference a hoisted opts name we've seen pin algorithms, accept.
        # Look at every identifier passed positionally; if any matches a known
        # safe-opts decl, accept the call.
        accepted_via_hoist = False
        for ident in re.findall(r"(?:^|[,(\s])([A-Za-z_$][\w$]*)\s*(?=[,)])", args):
            if ident in safe_opts_names:
                accepted_via_hoist = True
                break
        if accepted_via_hoist:
            continue

        findings.append(
            f"{path}:{lineno_for(m.start())}: jsonwebtoken.verify called "
            f"without pinning algorithms allowlist (CWE-327, JWT alg confusion); "
            f"pass {{ algorithms: ['HS256'] }} or similar"
        )
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    exts = (".js", ".mjs", ".cjs", ".ts", ".tsx")
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(exts):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
