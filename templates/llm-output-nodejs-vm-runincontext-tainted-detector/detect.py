#!/usr/bin/env python3
"""
llm-output-nodejs-vm-runincontext-tainted-detector

Flags JavaScript / TypeScript source where Node's ``vm`` module
executes a runtime-built code string. The ``vm`` module is widely
mistaken for a sandbox; the Node docs are explicit that it is *not*
a security boundary. Combining it with a runtime-built code string
gives the attacker arbitrary code execution in the host process,
which is the canonical CWE-94 (Code Injection) shape in Node.

Flagged call shapes (all members of the ``vm`` import / require):

* ``vm.runInNewContext(code, ...)``
* ``vm.runInContext(code, ...)``
* ``vm.runInThisContext(code, ...)``
* ``vm.compileFunction(code, ...)``
* ``new vm.Script(code, ...)``  (and ``new Script(code, ...)`` when
  imported by name)

A finding is emitted when the *first positional argument* (``code``)
is not a plain string literal. Bare idents, template literals that
contain a ``${...}`` interpolation, ``+`` concatenation, ``String(...)``,
``.toString()``, ``await`` expressions, function calls, etc. are all
treated as runtime-built. A template literal with **no** interpolation
is considered a literal.

Suppress with a trailing ``// llm-allow:nodejs-vm-tainted`` on the
relevant call line, or anywhere within the same statement.

Stdlib only. Reads files passed on argv (or recurses into directories
for ``*.js``, ``*.mjs``, ``*.cjs``, ``*.ts``, ``*.tsx``, ``*.md``,
``*.markdown``). Exit code 1 if any findings, 0 otherwise, 2 on usage
error.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

SUPPRESS = "llm-allow:nodejs-vm-tainted"

SCAN_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".md", ".markdown")

# vm members that take a code string as their first positional argument.
VM_METHODS = (
    "runInNewContext",
    "runInContext",
    "runInThisContext",
    "compileFunction",
)

# Constructor names that take code as first arg.
VM_CTORS = ("Script",)


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_JS_LANGS = {"js", "javascript", "ts", "typescript", "node", "mjs", "cjs", "tsx", "jsx"}


def _iter_js_blocks(text: str) -> Iterable[Tuple[str, int]]:
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _JS_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. // line and /* */ block. Strings (', ", `) are skipped
# so a comment marker inside a string literal is not treated as a comment.
# Template literals are tracked with single-level brace counting for
# ${ ... } interpolations.
# ---------------------------------------------------------------------------
def _mask_comments(text: str) -> str:
    """Mask // and /* */ comments AND the *interior* of string and
    template literals (preserving newlines so line numbers stay
    stable). The opening / closing quote characters themselves are
    preserved so downstream code can still recognize a literal arg.
    Inside a template literal, the body of ${...} interpolations is
    kept (it is real code).
    """
    out = []
    i = 0
    n = len(text)
    in_str = None  # None | '"' | "'"
    in_tpl = False
    tpl_brace_depth = 0  # depth of ${ ... } inside a template literal
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_str is not None:
            if c == "\\" and i + 1 < n:
                # mask both chars but keep newline if escaped char was \n
                out.append(" ")
                out.append(" " if text[i + 1] != "\n" else "\n")
                i += 2
                continue
            if c == in_str:
                out.append(c)
                in_str = None
                i += 1
                continue
            out.append(c if c == "\n" else " ")
            i += 1
            continue
        if in_tpl:
            if tpl_brace_depth > 0:
                # inside ${ ... }: real code, keep verbatim
                out.append(c)
                if c == "{":
                    tpl_brace_depth += 1
                elif c == "}":
                    tpl_brace_depth -= 1
                i += 1
                continue
            if c == "\\" and i + 1 < n:
                out.append(" ")
                out.append(" " if text[i + 1] != "\n" else "\n")
                i += 2
                continue
            if c == "$" and nxt == "{":
                # opening of an interpolation
                out.append("$")
                out.append("{")
                tpl_brace_depth = 1
                i += 2
                continue
            if c == "`":
                out.append(c)
                in_tpl = False
                i += 1
                continue
            out.append(c if c == "\n" else " ")
            i += 1
            continue
        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "`":
            in_tpl = True
            out.append(c)
            i += 1
            continue
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            if j < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                seg = text[i:]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = n
            else:
                seg = text[i : j + 2]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Argument-classification: is the first positional arg a static literal?
# We accept:
#   * "..." or '...' — plain string literal
#   * `...` — template literal with NO ${ ... } interpolation
# Everything else — treat as runtime-built.
# ---------------------------------------------------------------------------
def _is_static_string(arg: str) -> bool:
    s = arg.strip()
    if not s:
        return False
    if (s.startswith('"') and s.endswith('"') and len(s) >= 2) or (
        s.startswith("'") and s.endswith("'") and len(s) >= 2
    ):
        # Reject if it spans multiple top-level tokens (concatenation).
        # The split-on-+ is a coarse check, but we run after the split
        # so this branch sees a single arg slice already.
        return True
    if s.startswith("`") and s.endswith("`") and len(s) >= 2:
        body = s[1:-1]
        # Look for ${ that is not escaped.
        i = 0
        while i < len(body):
            if body[i] == "\\":
                i += 2
                continue
            if body[i] == "$" and i + 1 < len(body) and body[i + 1] == "{":
                return False
            i += 1
        return True
    return False


# ---------------------------------------------------------------------------
# Find balanced argument span starting at index of '('.
# ---------------------------------------------------------------------------
def _balanced_paren_end(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level_commas(text: str) -> List[str]:
    out: List[str] = []
    depth_p = 0
    depth_b = 0
    depth_c = 0
    cur = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth_p += 1
        elif c == ")":
            depth_p -= 1
        elif c == "[":
            depth_b += 1
        elif c == "]":
            depth_b -= 1
        elif c == "{":
            depth_c += 1
        elif c == "}":
            depth_c -= 1
        elif c == "," and depth_p == depth_b == depth_c == 0:
            out.append(text[cur:i])
            cur = i + 1
        i += 1
    out.append(text[cur:])
    return out


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _statement_end(text: str, start: int) -> int:
    depth_p = 0
    depth_b = 0
    depth_c = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth_p += 1
        elif c == ")":
            depth_p -= 1
        elif c == "[":
            depth_b += 1
        elif c == "]":
            depth_b -= 1
        elif c == "{":
            depth_c += 1
        elif c == "}":
            depth_c -= 1
        elif c in (";", "\n") and depth_p == depth_b == depth_c == 0:
            # Conservative: take the next ; OR end-of-line at depth 0.
            if c == ";":
                return i + 1
            # newline only counts when next non-space is not a method
            # continuation. Simplification: take the newline.
            # But to allow chained `.then(...)` lines, we keep going
            # only on bare newlines if the next non-ws char starts
            # something other than '.', ')', ',', '?'. Cheap proxy:
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            if j >= n or text[j] not in ".)],?":
                return i + 1
        i += 1
    return n


def _has_suppress(raw: str, span_start: int, span_end: int) -> bool:
    eol = raw.find("\n", span_end)
    if eol < 0:
        eol = len(raw)
    return SUPPRESS in raw[span_start:eol]


# ---------------------------------------------------------------------------
# Detector core.
# ---------------------------------------------------------------------------
# Match `<base>.<method>(`  where base is `vm` or any ident that we
# *guess* is the vm module. We accept the ident `vm` only — other
# import alias names are out of scope for this detector (covered by
# README "Limits"). Also match `runInNewContext(` etc. directly when
# imported as a named binding.
_METHOD_DOT_RE = re.compile(
    r"\bvm\s*\.\s*(" + "|".join(VM_METHODS) + r")\s*\("
)
_METHOD_BARE_RE = re.compile(
    r"(?<![A-Za-z0-9_$.])(" + "|".join(VM_METHODS) + r")\s*\("
)
_NEW_SCRIPT_RE = re.compile(
    r"\bnew\s+(?:vm\s*\.\s*)?(" + "|".join(VM_CTORS) + r")\s*\("
)

# Named-import detection. Bare-method matches only fire if the file
# actually pulls one of the VM_METHODS (or VM_CTORS) in as a named
# import / destructured require from `vm` or `node:vm`. Otherwise a
# user-defined method called `runInNewContext` on an unrelated object
# would produce a false positive.
_VM_NAMED_IMPORT_RE = re.compile(
    r"""
    (?:
      # ESM:  import { runInNewContext, Script } from 'node:vm';
      import\s*\{[^}]*\}\s*from\s*['"]node:vm['"]
    | import\s*\{[^}]*\}\s*from\s*['"]vm['"]
      # CJS:  const { runInNewContext } = require('vm');
    | (?:const|let|var)\s*\{[^}]*\}\s*=\s*require\s*\(\s*['"](?:node:)?vm['"]\s*\)
    )
    """,
    re.VERBOSE | re.DOTALL,
)


def _file_has_vm_named_binding(raw: str, name: str) -> bool:
    """Return True if `raw` (unmasked source) contains a named import /
    destructured require from 'vm' / 'node:vm' that pulls in `name`."""
    for m in _VM_NAMED_IMPORT_RE.finditer(raw):
        if re.search(r"\b" + re.escape(name) + r"\b", m.group(0)):
            return True
    return False


def _scan_block(
    raw: str,
    masked: str,
    line_offset: int,
    findings: List[Tuple[int, str, str, str]],
) -> None:
    seen: set = set()  # (start_idx) to dedupe between bare/dotted regexes

    def _emit(call_start: int, code: str, kind: str, prog_name: str) -> None:
        open_paren = masked.find("(", call_start)
        if open_paren < 0:
            return
        close_paren = _balanced_paren_end(masked, open_paren)
        if close_paren < 0:
            return
        inner = masked[open_paren + 1 : close_paren]
        args = _split_top_level_commas(inner)
        if not args:
            return
        first = args[0]
        if _is_static_string(first):
            return
        stmt_end = _statement_end(masked, close_paren + 1)
        if _has_suppress(raw, call_start, stmt_end):
            return
        if call_start in seen:
            return
        seen.add(call_start)
        line = _line_of(raw, call_start) + line_offset
        snippet_end = min(close_paren + 1, call_start + 200)
        snippet = raw[call_start:snippet_end].splitlines()[0]
        findings.append((line, code, f"{prog_name} with runtime-built code (CWE-94)", snippet))

    for m in _METHOD_DOT_RE.finditer(masked):
        _emit(m.start(), f"nodejs-vm-{m.group(1).lower()}-tainted", "dotted", f"vm.{m.group(1)}")
    for m in _METHOD_BARE_RE.finditer(masked):
        # skip if this is part of a dotted member access — already
        # handled by _METHOD_DOT_RE.
        idx = m.start()
        k = idx - 1
        while k >= 0 and masked[k] in " \t":
            k -= 1
        if k >= 0 and masked[k] == ".":
            continue
        # require an actual named import / destructured require so
        # we don't flag user-defined methods that happen to share a
        # name with a vm export.
        if not _file_has_vm_named_binding(raw, m.group(1)):
            continue
        _emit(m.start(), f"nodejs-vm-{m.group(1).lower()}-tainted", "bare", m.group(1))
    for m in _NEW_SCRIPT_RE.finditer(masked):
        _emit(m.start(), "nodejs-vm-script-tainted", "new", f"new {m.group(1)}")


def scan_text(text: str) -> List[Tuple[int, str, str, str]]:
    findings: List[Tuple[int, str, str, str]] = []
    masked = _mask_comments(text)
    _scan_block(text, masked, 0, findings)
    for body, off in _iter_js_blocks(text):
        masked_body = _mask_comments(body)
        _scan_block(body, masked_body, off, findings)
    findings.sort(key=lambda x: x[0])
    return findings


def scan_path(path: str) -> List[Tuple[str, int, str, str, str]]:
    out: List[Tuple[str, int, str, str, str]] = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name.endswith(SCAN_SUFFIXES):
                    full = os.path.join(root, name)
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as fh:
                            text = fh.read()
                    except OSError:
                        continue
                    for f in scan_text(text):
                        out.append((full, *f))
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return out
    for f in scan_text(text):
        out.append((path, *f))
    return out


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py PATH [PATH ...]\n"
            "  Scans JS/TS for vm.runIn*Context / vm.compileFunction /\n"
            "  new vm.Script with a runtime-built code string (CWE-94).",
            file=sys.stderr,
        )
        return 2
    any_finding = False
    for path in argv[1:]:
        for fpath, line, code, msg, snip in scan_path(path):
            any_finding = True
            print(f"{fpath}:{line}: {code}: {msg}: {snip}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
