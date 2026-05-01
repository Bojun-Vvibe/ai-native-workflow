#!/usr/bin/env python3
"""Detect dynamic-code-execution sinks in TypeScript / JavaScript.

Flags calls to ``eval(...)``, ``new Function(...)``,
``vm.runInNewContext(...)``, ``vm.runInThisContext(...)``,
``vm.runInContext(...)``, and ``vm.compileFunction(...)`` that take
any non-string-literal argument. These are CWE-95 (eval injection) /
CWE-94 (code injection) sinks: when the argument is attacker-influenced
the program executes arbitrary code.

Heuristic:

* String- and template-literal bodies are blanked so an inner ``eval``
  inside a quoted string does not match.
* Single-line (``//``) and block (``/* */``) comments are blanked.
* A call ``eval("literal-string")`` (single arg, single quoted/template
  string literal, no concatenation) is treated as benign — it is still
  ugly but not LLM-emitted-from-untrusted-input shape.
* Same exemption for ``new Function("...literal...")`` with all string
  arguments that are pure literals (no ``${}`` interpolation, no
  concatenation operator).
* ``vm.*`` calls are always flagged — there is no benign literal use.
* Suppression marker (per-line, in a comment):
  ``// llm-allow:ts-eval``.

The detector also extracts fenced ``ts`` / ``tsx`` / ``js`` / ``jsx``
code blocks from Markdown so README worked examples and docs are
scanned consistently.

Usage::

    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:ts-eval"
SCAN_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                 ".md", ".markdown")

# --- token-aware blanking -------------------------------------------------

_STR_RE = re.compile(
    r"""
    (?P<bs>  /\*.*?\*/                  ) |   # block comment
    (?P<ls>  //[^\n]*                   ) |   # line comment
    (?P<dq>  "(?:\\.|[^"\\\n])*"        ) |   # double-quoted
    (?P<sq>  '(?:\\.|[^'\\\n])*'        ) |   # single-quoted
    (?P<tp>  `(?:\\.|[^`\\])*`          )     # template literal
    """,
    re.VERBOSE | re.DOTALL,
)


def _blank(src: str) -> str:
    """Replace comment / string bodies with same-length spaces.

    Newlines are preserved so line numbers stay correct.
    """
    out = []
    i = 0
    for m in _STR_RE.finditer(src):
        out.append(src[i:m.start()])
        body = m.group(0)
        out.append("".join(c if c == "\n" else " " for c in body))
        i = m.end()
    out.append(src[i:])
    return "".join(out)


# --- markdown fence extraction -------------------------------------------

_FENCE_RE = re.compile(
    r"^```\s*(ts|tsx|typescript|js|jsx|javascript|node)\b[^\n]*\n"
    r"(?P<body>.*?)"
    r"^```",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _extract_md_blocks(src: str) -> str:
    """Pull ts/js fenced blocks out of Markdown, preserve line offsets."""
    out_lines = src.splitlines(keepends=True)
    keep = [" " * (len(l) - 1) + "\n" if l.endswith("\n") else " " * len(l)
            for l in out_lines]
    for m in _FENCE_RE.finditer(src):
        # Map char offset -> line index
        start_line = src.count("\n", 0, m.start("body"))
        body = m.group("body")
        body_lines = body.splitlines(keepends=True)
        for j, bl in enumerate(body_lines):
            idx = start_line + j
            if idx < len(keep):
                keep[idx] = bl
    return "".join(keep)


# --- sink detection -------------------------------------------------------

# eval(  or  new Function(  or  vm.runIn*(  or  vm.compileFunction(
_SINK_RE = re.compile(
    r"""
    (?<![\w.$])                                       # no identifier left-context
    (
        eval                                          |
        new\s+Function                                |
        vm\.runInNewContext                           |
        vm\.runInThisContext                          |
        vm\.runInContext                              |
        vm\.compileFunction                           |
        Function                                          # bare Function constructor call
    )
    \s*\(
    """,
    re.VERBOSE,
)

# A "literal-only argument list": one or more string literals separated by
# commas, possibly with whitespace. No ${} interpolation, no + concat, no
# identifiers. Used to whitelist eval("alert('hi')") in pure-demo code.
_LITERAL_ARGS_RE = re.compile(
    r"""
    \s*
    (
        "(?:\\.|[^"\\\n])*"
      | '(?:\\.|[^'\\\n])*'
      | `[^`$]*`
    )
    \s*
    (?: , \s*
        (
            "(?:\\.|[^"\\\n])*"
          | '(?:\\.|[^'\\\n])*'
          | `[^`$]*`
        )
        \s*
    )*
    \)
    """,
    re.VERBOSE,
)


def _find_call_args(src: str, open_paren_idx: int):
    """Return (args_text, end_idx_after_close_paren) or (None, None)."""
    depth = 0
    i = open_paren_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren_idx + 1:i], i + 1
        i += 1
    return None, None


def _scan(text: str, path: Path):
    findings = []
    md = path.suffix.lower() in (".md", ".markdown")
    src = _extract_md_blocks(text) if md else text
    blanked = _blank(src)
    raw_lines = text.splitlines()

    for m in _SINK_RE.finditer(blanked):
        sink_name = re.sub(r"\s+", " ", m.group(1))
        # locate the '('
        open_idx = blanked.find("(", m.end() - 1)
        if open_idx < 0:
            continue
        args_text, _end = _find_call_args(blanked, open_idx)
        if args_text is None:
            continue

        # In ORIGINAL source for literal check (blanked has spaces inside strings).
        orig_args, _ = _find_call_args(src, open_idx)
        line_no = blanked.count("\n", 0, m.start()) + 1

        # Suppression check
        if line_no - 1 < len(raw_lines) and SUPPRESS in raw_lines[line_no - 1]:
            continue

        # vm.* always flagged
        is_vm = sink_name.startswith("vm.")
        is_function_ctor = sink_name in ("new Function", "Function")

        if not is_vm:
            # If args are pure literal(s) AND no template interpolation, exempt.
            stripped = (orig_args or "").strip()
            if stripped and _LITERAL_ARGS_RE.fullmatch(stripped + ")"):
                # extra: reject ${} interpolation in template literals
                if "${" not in stripped:
                    continue

        kind = "ts-eval-sink"
        if is_vm:
            kind = "ts-vm-eval-sink"
        elif is_function_ctor:
            kind = "ts-function-ctor-sink"

        findings.append(f"{path}:{line_no}: {kind}({sink_name})")

    return findings


def _iter_paths(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for q in sorted(p.rglob("*")):
                if q.is_file() and q.suffix.lower() in SCAN_SUFFIXES:
                    yield q
        elif p.is_file():
            yield p


def main(argv):
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings = []
    for path in _iter_paths(argv[1:]):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"{path}: read-error: {e}", file=sys.stderr)
            continue
        findings.extend(_scan(text, path))
    for f in findings:
        print(f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
