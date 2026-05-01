#!/usr/bin/env python3
"""
llm-output-rust-command-shell-tainted-detector

Flags Rust source where ``std::process::Command`` (or its re-export
``tokio::process::Command``) is used to invoke a shell interpreter
(``sh``, ``bash``, ``zsh``, ``cmd``, ``cmd.exe``, ``powershell``,
``pwsh``) with ``-c`` / ``/C`` and an argument that is a runtime-built
string — typically a ``format!``, a ``+`` concatenation, a
``String::from`` of a function result, or a bare identifier.

This is the canonical CWE-78 (OS Command Injection) shape in Rust.
A LLM under "make subprocess work" pressure tends to write::

    Command::new("sh").arg("-c").arg(format!("ls {}", user)).output()?;

instead of the safe shape::

    Command::new("ls").arg(user).output()?;          // argv form
    // or, if a shell really is required:
    Command::new("sh").arg("-c").arg("ls --").arg(user).output()?;

The detector flags two kinds:

1. **rust-command-shell-tainted** — a ``Command::new("<shell>")``
   chain that contains ``.arg("-c")`` (or ``.arg("/C")`` for ``cmd``)
   AND whose final ``.arg(...)`` argument is *not* a plain string
   literal. Bare idents, ``format!(...)``, ``concat!(...)``,
   ``String::from(...)``, ``.to_string()``, ``&s``, and ``s + ...``
   are all treated as runtime-built.

2. **rust-command-shell-arg-format** — any single ``.arg(format!(...))``
   chained onto a ``Command`` whose program is one of the shells
   above, even without a ``-c`` (covers Windows ``powershell -Command``
   patterns where ``-Command`` is sometimes spelled differently).

A finding is suppressed if the same statement carries the trailing
comment ``// llm-allow:rust-command-shell``. Single-line ``//``
comments and ``/* ... */`` block comments are masked before analysis.
String literal interiors are NOT analyzed for injection (we only
care about how the command was *built*).

Fenced ``rust`` / ``rs`` code blocks are extracted from Markdown.

Stdlib only. Reads files passed on argv (or recurses into directories
for *.rs / *.md / *.markdown). Exit code 1 if any findings, 0
otherwise, 2 on usage error.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

SUPPRESS = "// llm-allow:rust-command-shell"

SCAN_SUFFIXES = (".rs", ".md", ".markdown")

SHELLS = (
    "sh",
    "bash",
    "zsh",
    "ash",
    "dash",
    "ksh",
    "/bin/sh",
    "/bin/bash",
    "/bin/zsh",
    "/usr/bin/sh",
    "/usr/bin/bash",
    "/usr/bin/env",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
)


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_RUST_LANGS = {"rust", "rs"}


def _iter_rust_blocks(text: str) -> Iterable[Tuple[str, int]]:
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _RUST_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. Replace // line comments and /* */ block comments with
# spaces, preserving newlines so line numbers stay stable.
# ---------------------------------------------------------------------------
def _mask_comments(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            # line comment — keep the // (so SUPPRESS marker still
            # readable downstream is not needed; we capture it via the
            # raw line below). Replace body with spaces.
            j = text.find("\n", i)
            if j < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                # unterminated, mask to end
                seg = text[i:]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = n
            else:
                seg = text[i : j + 2]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Detector core.
#
# Strategy: find each ``Command::new("...")`` call site, then walk
# forward through chained ``.arg(...)`` / ``.args(...)`` calls (across
# newlines) until the chain ends (``;``, ``?`` followed by whitespace
# and a non-method token, or top-level ``)`` that closes a wrapping
# expression). We collect:
#   * the program string (if literal)
#   * each .arg(...) inner expression (raw text)
#
# Then classify.
# ---------------------------------------------------------------------------

_NEW_RE = re.compile(
    r"\b(?:tokio::process::|std::process::|process::)?Command\s*::\s*new\s*\(\s*"
    r'(?P<prog>"(?:[^"\\]|\\.)*")\s*\)',
)

_METHOD_RE = re.compile(r"\.\s*(arg|args)\s*\(")


def _balanced_paren_end(text: str, start: int) -> int:
    """Given index of '(' at start, return index of matching ')'.
    Returns -1 if unbalanced. Handles nested parens and string literals."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            # skip string literal (handle \")
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == "'":
            # rust char or lifetime; just step over
            i += 1
            continue
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 0:
                return i
            i += 1
            continue
        i += 1
    return -1


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


_LITERAL_STR_RE = re.compile(r'^"(?:[^"\\]|\\.)*"$')


def _arg_is_literal_str(arg_text: str) -> bool:
    s = arg_text.strip()
    return bool(_LITERAL_STR_RE.match(s))


def _arg_looks_runtime_built(arg_text: str) -> bool:
    """True if the arg expression is clearly NOT a static string literal:
    bare ident, format!, concat of !=concat! macro, String::from(...),
    .to_string(), .to_owned(), method call result, ``a + b``, ``&x``
    on a non-literal, etc.
    """
    s = arg_text.strip()
    if not s:
        return False
    if _arg_is_literal_str(s):
        return False
    # &"static"  -> still a literal-ish; not runtime-built
    if s.startswith("&") and _arg_is_literal_str(s[1:].lstrip()):
        return False
    # concat!("a", "b") with all literal arms — treat as static
    if s.startswith("concat!"):
        inner_open = s.find("(")
        inner_close = s.rfind(")")
        if inner_open >= 0 and inner_close > inner_open:
            inner = s[inner_open + 1 : inner_close]
            arms = [a.strip() for a in inner.split(",") if a.strip()]
            if all(_arg_is_literal_str(a) for a in arms):
                return False
    # Anything else (format!, ident, expression) — runtime.
    return True


def _scan_source(src: str, base_line: int, path: str) -> List[str]:
    findings: List[str] = []
    masked = _mask_comments(src)
    raw_lines = src.splitlines()
    for m in _NEW_RE.finditer(masked):
        prog = m.group("prog")
        try:
            prog_val = eval(prog)  # safe: regex constrained to "..." string
        except Exception:
            prog_val = ""
        if prog_val not in SHELLS:
            continue

        # Walk forward collecting .arg(...) / .args(...) inner texts.
        cursor = m.end()
        chain_end = cursor
        args: List[Tuple[str, str]] = []  # (method, inner)
        while True:
            mm = _METHOD_RE.search(masked, cursor)
            if not mm:
                break
            # Between cursor and mm.start(), only whitespace, ?, or
            # comment masking is allowed for it to still count as the
            # same chain.
            between = masked[cursor : mm.start()]
            if not re.fullmatch(r"[\s\?]*", between):
                break
            method = mm.group(1)
            paren_open = mm.end() - 1  # mm matched "...arg(" / "...args("
            paren_close = _balanced_paren_end(masked, paren_open)
            if paren_close < 0:
                break
            inner = masked[paren_open + 1 : paren_close]
            args.append((method, inner))
            cursor = paren_close + 1
            chain_end = cursor

        if not args:
            continue

        # Detect ``-c`` / ``/C`` literal among the args, and remember
        # its index. The "script" slot is the .arg() IMMEDIATELY after
        # the -c marker, not the last arg in the chain (callers may
        # pass extra positional args after -c, which the shell binds
        # to $0/$1/...).
        dash_c_idx = -1
        arg_only_idx = -1
        DASH_C_FORMS = {'"-c"', '"-C"', '"/C"', '"/c"', "'-c'"}
        for k, (meth, inner) in enumerate(args):
            if meth != "arg":
                continue
            arg_only_idx += 1
            s = inner.strip()
            if s in DASH_C_FORMS or s.replace(" ", "") in DASH_C_FORMS:
                dash_c_idx = k
                break
        has_dash_c = dash_c_idx >= 0

        # Suppress check: extend the window past chain_end to the next
        # ``;`` or end-of-line, so trailing ``// llm-allow:...`` markers
        # on the closing line are captured.
        sup_end = chain_end
        n_src = len(src)
        # walk to end of statement
        while sup_end < n_src and src[sup_end] not in (";", "\n"):
            sup_end += 1
        if sup_end < n_src and src[sup_end] == ";":
            # include rest of line after ;
            nl = src.find("\n", sup_end)
            sup_end = nl if nl >= 0 else n_src
        # Also include any allow marker on lines that contain a chained
        # .arg(...) call — markers are sometimes placed on the .arg line.
        raw_call_window = src[m.start() : sup_end]
        if SUPPRESS in raw_call_window:
            continue
        # Per-arg trailing comment: scan each arg's source line.
        any_arg_suppressed = False
        for meth, inner in args:
            # crude: locate inner inside src, check rest of that line.
            idx = src.find(inner, m.start(), sup_end)
            if idx < 0:
                continue
            line_end = src.find("\n", idx)
            if line_end < 0:
                line_end = n_src
            if SUPPRESS in src[idx:line_end]:
                any_arg_suppressed = True
                break
        if any_arg_suppressed:
            continue

        line_no = _line_of(src, m.start()) + base_line
        snippet = raw_lines[line_no - base_line - 1].strip()
        if len(snippet) > 100:
            snippet = snippet[:97] + "..."

        if has_dash_c:
            # Find the .arg() *immediately* after dash_c_idx.
            script_inner = None
            for meth, inner in args[dash_c_idx + 1 :]:
                if meth == "arg":
                    script_inner = inner
                    break
            if script_inner is not None and _arg_looks_runtime_built(script_inner):
                findings.append(
                    f"{path}:{line_no}: rust-command-shell-tainted: "
                    f"Command::new({prog!s}) ... -c with runtime-built script (CWE-78): {snippet}"
                )
                continue

        # No -c or -c with literal script: still flag any .arg(format!(...))
        # since powershell-style invocations sometimes skip -c.
        for meth, inner in args:
            if meth != "arg":
                continue
            if "format!" in inner and _arg_looks_runtime_built(inner):
                findings.append(
                    f"{path}:{line_no}: rust-command-shell-arg-format: "
                    f"Command::new({prog!s}) with .arg(format!(...)) (CWE-78): {snippet}"
                )
                break

    return findings


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if path.endswith((".md", ".markdown")):
        for body, off in _iter_rust_blocks(text):
            findings.extend(_scan_source(body, off, path))
    else:
        findings.extend(_scan_source(text, 0, path))
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(SCAN_SUFFIXES):
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
