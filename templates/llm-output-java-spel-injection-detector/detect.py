#!/usr/bin/env python3
"""
llm-output-java-spel-injection-detector

Flags Java code that parses a Spring Expression Language (SpEL)
expression built from a non-literal value. SpEL is a fully featured
expression language: a parsed-and-evaluated SpEL string can invoke
arbitrary Java methods (`T(java.lang.Runtime).getRuntime().exec(...)`),
which makes any unconstrained `parser.parseExpression(<dynamic>)`
followed by `.getValue(...)` a CWE-94 (code injection) sink.

LLMs love this anti-pattern when asked "evaluate a user-supplied
formula in Spring": the model reaches for `SpelExpressionParser`,
concatenates the request parameter into the expression text, and
evaluates it against a fresh `StandardEvaluationContext` (which is
permissive by default and exposes type references).

What this flags
---------------
A finding is emitted when the file references SpEL (`SpelExpressionParser`
or `org.springframework.expression`) AND any of:

1. `parser.parseExpression(...)` whose argument is not a single
   string literal — i.e. it contains `+`, a method call, or a bare
   identifier.
2. `parseExpression` called on a value that came from a parameter
   annotated `@RequestParam`, `@PathVariable`, `@RequestBody`,
   `@RequestHeader`, or a `HttpServletRequest.getParameter(...)`
   chain in the same file (heuristic: those names appear in the
   argument expression).
3. Any `parseExpression(...).getValue(...)` chain that hands a
   `StandardEvaluationContext` (the permissive default that exposes
   type references) when the parsed expression is non-literal.

What this does NOT flag
-----------------------
* `parser.parseExpression("'hello ' + name")` — pure string literal
  (no concatenation, no identifier).
* SpEL evaluation against `SimpleEvaluationContext.forReadOnlyDataBinding()`
  with a *literal* expression.
* Files that don't reference SpEL at all (the bare token `parseExpression`
  could be anything else).

Stdlib only. Reads files passed on argv (or recurses into directories).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Anchor: file must reference SpEL.
_SPEL_PRESENT_RE = re.compile(
    r"\b(?:SpelExpressionParser|org\.springframework\.expression)\b"
)

# parseExpression(<args>). Group 1 = args. Paren-balanced one level deep.
_PARSE_CALL_RE = re.compile(
    r"\bparseExpression\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)

# A pure single string literal argument: optional whitespace, then
# "...." with escapes, then optional whitespace. No + concatenation,
# no identifiers.
_PURE_STRING_LITERAL_RE = re.compile(
    r'^\s*"(?:[^"\\]|\\.)*"\s*$'
)

# Tainted-source identifiers commonly seen in Spring web handlers.
_TAINT_HINT_RE = re.compile(
    r"""(?x)
    \b(?:
        getParameter
      | getHeader
      | getQueryString
      | getRequestURI
      | request\.getInputStream
      | RequestParam
      | PathVariable
      | RequestBody
      | RequestHeader
      | ServletRequest
    )\b
    """
)

# StandardEvaluationContext = permissive default, allows T(...) refs.
_PERMISSIVE_CTX_RE = re.compile(r"\bStandardEvaluationContext\b")

# A bare-identifier or method-call argument — i.e. *not* a literal.
# We treat any argument that is not _PURE_STRING_LITERAL_RE as
# potentially dynamic, but only flag in combination with other signals.
_HAS_PLUS_RE = re.compile(r'"\s*\+|\+\s*"|\+\s*\w')


def _line_no(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def _looks_tainted_window(text: str, off: int) -> bool:
    """Look in a 400-char window before the call for tainted sources."""
    window = text[max(0, off - 400) : off]
    return bool(_TAINT_HINT_RE.search(window))


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _SPEL_PRESENT_RE.search(text):
        return findings

    permissive = bool(_PERMISSIVE_CTX_RE.search(text))

    for m in _PARSE_CALL_RE.finditer(text):
        args = m.group(1).strip()
        if not args:
            continue
        if _PURE_STRING_LITERAL_RE.match(args):
            # Pure literal — only risky if combined with an explicit
            # exec sink, which we don't try to track here.
            continue

        line = _line_no(text, m.start())
        # Case A: explicit string concatenation in the argument.
        if _HAS_PLUS_RE.search(args):
            findings.append(
                f"{path}:{line}: SpEL parseExpression with concatenated "
                f"argument (CWE-94 code injection): {args[:80]!s}"
            )
            continue

        # Case B: argument references a tainted-looking name.
        if _TAINT_HINT_RE.search(args):
            findings.append(
                f"{path}:{line}: SpEL parseExpression with request-derived "
                f"argument (CWE-94 code injection): {args[:80]!s}"
            )
            continue

        # Case C: bare identifier argument and a tainted source visible
        # anywhere earlier in the same file (parameter annotation,
        # request.getParameter, getHeader, etc.).
        if _looks_tainted_window(text, m.start()) or _TAINT_HINT_RE.search(text[: m.start()]):
            ctx_note = " under StandardEvaluationContext" if permissive else ""
            findings.append(
                f"{path}:{line}: SpEL parseExpression with non-literal "
                f"argument{ctx_note} (CWE-94 code injection): {args[:80]!s}"
            )

    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(".java") or f.endswith(".java.txt"):
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
