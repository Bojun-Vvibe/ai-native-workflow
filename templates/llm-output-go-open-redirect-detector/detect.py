#!/usr/bin/env python3
"""
llm-output-go-open-redirect-detector

Flags Go HTTP handlers that pass user-controlled input straight into
http.Redirect / w.Header().Set("Location", ...) without validating that
the destination is on an allow-list. This is the canonical CWE-601
(URL Redirection to Untrusted Site, "Open Redirect") shape.

LLMs love to emit this when asked to write a "?next=" / "?return_to="
post-login redirect: they read the query parameter and hand it directly
to http.Redirect, which happily issues a 302 to attacker.example.com.

Heuristic: a finding is emitted when, in the same function body, we see

  1. A read of user input from one of:
        r.URL.Query().Get(...)
        r.FormValue(...)
        r.PostFormValue(...)
        r.URL.Query()[...]
        mux.Vars(r)[...]
     ... captured into an identifier (or used inline).

  2. That identifier (or a +concat of it, or fmt.Sprintf with it)
     is then passed as the destination argument of one of:
        http.Redirect(w, r, <dest>, code)
        w.Header().Set("Location", <dest>)
        w.Header().Add("Location", <dest>)

We deliberately do NOT flag redirects whose destination is a string
literal, a path that starts with "/" with no host, or an obvious
allow-list lookup (`allowed[next]`, `validateRedirect(next)`).

Stdlib only. Reads files passed on argv (or recurses into directories).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Set, Tuple

# Untrusted-input source patterns. Capture group 1 is the var name (if any).
_SOURCE_ASSIGN_RE = re.compile(
    r"""(?x)
    \b
    ([A-Za-z_]\w*)            # 1: ident
    \s*:?=\s*
    (?:
        [a-zA-Z_]\w*\.URL\.Query\(\)\.Get\([^)]*\)
      | [a-zA-Z_]\w*\.FormValue\([^)]*\)
      | [a-zA-Z_]\w*\.PostFormValue\([^)]*\)
      | [a-zA-Z_]\w*\.URL\.Query\(\)\[[^\]]+\](?:\[\d+\])?
      | mux\.Vars\([^)]*\)\[[^\]]+\]
    )
    """
)

# Inline source expressions (no assignment) we recognize when they appear
# directly inside a redirect call.
_SOURCE_INLINE_RE = re.compile(
    r"""(?x)
    (?:
        [a-zA-Z_]\w*\.URL\.Query\(\)\.Get\([^)]*\)
      | [a-zA-Z_]\w*\.FormValue\([^)]*\)
      | [a-zA-Z_]\w*\.PostFormValue\([^)]*\)
      | mux\.Vars\([^)]*\)\[[^\]]+\]
    )
    """
)

# Sinks. Capture group 1 is the destination expression we will analyze.
_REDIRECT_RE = re.compile(
    r"""(?x)
    \bhttp\.Redirect\s*\(
        \s*[^,]+,\s*[^,]+,\s*           # w, r,
        ([^,]+?)                         # 1: dest expr
        ,\s*[^,)]+\)                     # status code
    """
)

_HEADER_LOC_RE = re.compile(
    r"""(?x)
    \b\w+\.Header\(\)\.(?:Set|Add)\s*\(
        \s*['"]Location['"]\s*,\s*
        ([^)]+?)                         # 1: dest expr
        \)
    """
)

# Markers that the destination has been deliberately validated. If any of
# these appear in the function body, we *suppress* the finding for that
# function (assume the author knew about open-redirects).
_ALLOWLIST_HINT_RE = re.compile(
    r"""(?x)
    (?:
        \ballowed[A-Za-z_]*\s*\[          # allowedHosts[...]
      | \bvalidate[A-Za-z_]*Redirect\b
      | \bisSafeRedirect\b
      | \bsafeRedirect\b
      | \burl\.Parse\(                    # net/url parse + Host check
      | \.Hostname\(\)\s*==
      | \bstrings\.HasPrefix\([^,]+,\s*['"]/['"]
    )
    """
)


def _split_funcs(text: str) -> List[Tuple[int, int, str]]:
    """Return (start_offset, end_offset, body) for each top-level Go func.
    A 'body' here is the brace-balanced span starting at the func's '{'.
    Tolerates strings and line comments; not a full parser."""
    out: List[Tuple[int, int, str]] = []
    n = len(text)
    i = 0
    while i < n:
        # find next "func"
        m = re.search(r"\bfunc\b", text[i:])
        if not m:
            break
        j = i + m.start()
        # find the opening '{' for this func
        k = text.find("{", j)
        if k == -1:
            break
        # brace-balance from k
        depth = 0
        p = k
        in_str = None
        while p < n:
            c = text[p]
            if in_str:
                if c == "\\" and in_str == '"' and p + 1 < n:
                    p += 2
                    continue
                if c == in_str:
                    in_str = None
                p += 1
                continue
            if c in '"`':
                in_str = c
                p += 1
                continue
            if c == "/" and p + 1 < n and text[p + 1] == "/":
                # line comment
                nl = text.find("\n", p)
                p = n if nl == -1 else nl
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append((j, p + 1, text[j : p + 1]))
                    p += 1
                    break
            p += 1
        i = p
    return out


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for fstart, _fend, body in _split_funcs(text):
        # Collect tainted idents in this function body.
        tainted: Set[str] = set()
        for am in _SOURCE_ASSIGN_RE.finditer(body):
            tainted.add(am.group(1))
        if not tainted and not _SOURCE_INLINE_RE.search(body):
            continue
        # Propagate taint: any assignment whose RHS references a tainted
        # ident or an inline source expression also becomes tainted. We
        # iterate to a fixed point (cheap; bodies are short).
        _ASSIGN_GENERIC = re.compile(
            r"\b([A-Za-z_]\w*)\s*:?=\s*([^\n;]+)"
        )
        changed = True
        while changed:
            changed = False
            for am in _ASSIGN_GENERIC.finditer(body):
                lhs, rhs = am.group(1), am.group(2)
                if lhs in tainted:
                    continue
                if _SOURCE_INLINE_RE.search(rhs):
                    tainted.add(lhs)
                    changed = True
                    continue
                for t in tainted:
                    if re.search(rf"\b{re.escape(t)}\b", rhs):
                        tainted.add(lhs)
                        changed = True
                        break
        # If the function has an obvious allow-list / validation hint,
        # assume the author handled it and skip.
        if _ALLOWLIST_HINT_RE.search(body):
            continue
        for sink_re, label in (
            (_REDIRECT_RE, "http.Redirect"),
            (_HEADER_LOC_RE, "Location header"),
        ):
            for sm in sink_re.finditer(body):
                dest = sm.group(1).strip()
                if _is_dest_tainted(dest, tainted):
                    # compute line number in original file
                    abs_off = fstart + sm.start()
                    line_no = text.count("\n", 0, abs_off) + 1
                    findings.append(
                        f"{path}:{line_no}: {label} destination is "
                        f"user-controlled (CWE-601 open redirect): "
                        f"dest={dest[:80]!s}"
                    )
    return findings


def _is_dest_tainted(dest: str, tainted: Set[str]) -> bool:
    # Direct match against a tainted ident.
    for t in tainted:
        if re.search(rf"\b{re.escape(t)}\b", dest):
            return True
    # Inline source expression as the destination.
    if _SOURCE_INLINE_RE.search(dest):
        return True
    # fmt.Sprintf("%s...", taintedVar) — the regex above already handles
    # ident matching; this branch is here so future maintainers see the
    # intent clearly.
    return False


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(".go") or f.endswith(".go.txt"):
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
