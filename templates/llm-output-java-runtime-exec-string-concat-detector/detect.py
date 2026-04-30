#!/usr/bin/env python3
"""Detect non-literal ``Runtime.exec`` / ``ProcessBuilder`` calls in Java.

LLMs emitting Java commonly write::

    Runtime.getRuntime().exec("sh -c " + userInput);
    new ProcessBuilder("git " + branch).start();
    Runtime.getRuntime().exec(String.format("ls %s", path));

All three are CWE-78 / CWE-88 in disguise. The single-string forms
tokenise on whitespace via ``StringTokenizer``, so any space in the
interpolated value becomes a new argv token (argument injection); when
the model wraps in ``sh -c`` to enable pipes, every shell metacharacter
in the interpolated value is interpreted by the shell.

What this flags
---------------
* ``Runtime.getRuntime().exec(<expr>)`` where ``<expr>`` is non-literal:
  contains ``+``, ``String.format(``, ``.formatted(``,
  ``MessageFormat.format(``, or is a bare identifier / method-call
  reference (e.g. ``cmd``, ``buildCmd()``).
* ``new ProcessBuilder(<expr>)`` with the same condition (single-arg
  form). Multi-arg argv form with all-literal arguments is allowed.
* ``Runtime.getRuntime().exec(new String[]{ ..., <expr>, ... })`` where
  any array element is non-literal.

What this does NOT flag
-----------------------
* ``Runtime.getRuntime().exec("ls -la /tmp")`` — fully literal.
* ``new ProcessBuilder("git", "status")`` — argv form, all literals.
* ``new ProcessBuilder(List.of("git", "status"))`` — argv form.
* Lines suffixed with ``// runtime-exec-ok``.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// runtime-exec-ok"

RE_RUNTIME_EXEC = re.compile(
    r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\("
)
RE_NEW_PROCESS_BUILDER = re.compile(r"\bnew\s+ProcessBuilder\s*\(")


def _strip_strings_and_comments(line: str) -> str:
    """Replace string-literal contents with spaces; drop ``//`` line comments.

    Java-flavoured: handles ``"..."`` and ``'.'`` char literals. Does not
    attempt to track ``/* ... */`` block comments across lines (line scanner).
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_c = False
    while i < n:
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
                out.append('"')
            else:
                out.append(" ")
        elif in_c:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_c = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == '"':
                in_s = True
                out.append('"')
            elif ch == "'":
                in_c = True
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _extract_call_args_text(stripped: str, paren_idx: int) -> str | None:
    """Return the text inside a balanced (...) starting at ``paren_idx``.

    ``paren_idx`` points at the ``(``. Only ``stripped`` (string contents
    blanked) is parsed. Returns None if parens are unbalanced on the line.
    """
    depth = 0
    start = paren_idx + 1
    for j in range(paren_idx, len(stripped)):
        c = stripped[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return stripped[start:j]
    return None


def _split_top_level_args(s: str) -> list[str]:
    """Split a comma list at the top paren / bracket / brace depth."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


# A "literal" arg, after string-blanking, looks like: just `""` (empty string
# placeholder = `"  "` in original collapsed to `""`). Since we replaced
# string contents with spaces but kept the quotes, a bare string literal
# becomes `"<spaces>"`.
RE_BARE_LITERAL = re.compile(r'^"\s*"$')

# Indicators of non-literal expression in an arg.
RE_INTERP_INDICATORS = re.compile(
    r"(?:\+)|(?:\bString\s*\.\s*format\s*\()|"
    r"(?:\.\s*formatted\s*\()|"
    r"(?:\bMessageFormat\s*\.\s*format\s*\()"
)
# An identifier-ish reference that's not just a string literal.
RE_BARE_IDENT = re.compile(r"^[A-Za-z_$][\w$]*(?:\s*\([^)]*\))?$")


def _arg_is_literal(arg: str) -> bool:
    a = arg.strip()
    if not a:
        return True  # empty arg list — not a non-literal
    if RE_BARE_LITERAL.match(a):
        return True
    return False


def _arg_is_unsafe(arg: str) -> bool:
    a = arg.strip()
    if RE_BARE_LITERAL.match(a):
        return False
    if RE_INTERP_INDICATORS.search(a):
        return True
    if RE_BARE_IDENT.match(a):
        return True
    # Anything else with no quotes at all is suspicious.
    if '"' not in a:
        return True
    # Mixed literal + something — also unsafe.
    return True


def _array_elements_unsafe(arg: str) -> bool:
    """If ``arg`` is ``new String[]{...}``, check elements for non-literal."""
    m = re.match(r"new\s+String\s*\[\s*\]\s*\{(.*)\}\s*$", arg.strip(), re.DOTALL)
    if not m:
        return False
    inner = m.group(1)
    elems = _split_top_level_args(inner)
    return any(_arg_is_unsafe(e) for e in elems)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        stripped = _strip_strings_and_comments(raw)

        # Runtime.getRuntime().exec(...)
        m = RE_RUNTIME_EXEC.search(stripped)
        if m:
            paren = m.end() - 1
            args_text = _extract_call_args_text(stripped, paren)
            if args_text is not None:
                args = _split_top_level_args(args_text)
                if args:
                    first = args[0]
                    if _array_elements_unsafe(first):
                        findings.append(
                            (path, lineno, "runtime-exec-array-interp", raw.rstrip())
                        )
                    elif _arg_is_unsafe(first):
                        findings.append(
                            (path, lineno, "runtime-exec-interp", raw.rstrip())
                        )
                    continue

        # new ProcessBuilder(...)
        m2 = RE_NEW_PROCESS_BUILDER.search(stripped)
        if m2:
            paren = m2.end() - 1
            args_text = _extract_call_args_text(stripped, paren)
            if args_text is not None:
                args = _split_top_level_args(args_text)
                if len(args) == 1:
                    first = args[0]
                    if _array_elements_unsafe(first):
                        findings.append(
                            (
                                path,
                                lineno,
                                "process-builder-array-interp",
                                raw.rstrip(),
                            )
                        )
                    elif _arg_is_unsafe(first):
                        findings.append(
                            (path, lineno, "process-builder-interp", raw.rstrip())
                        )
                else:
                    # Multi-arg argv form: flag if any single arg is unsafe.
                    for a in args:
                        if _arg_is_unsafe(a):
                            findings.append(
                                (
                                    path,
                                    lineno,
                                    "process-builder-argv-interp",
                                    raw.rstrip(),
                                )
                            )
                            break
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.java")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
