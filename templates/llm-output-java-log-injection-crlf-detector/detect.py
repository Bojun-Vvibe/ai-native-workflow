#!/usr/bin/env python3
"""Detect Java logger calls that splice unsanitised user input into a
log message — CWE-117 (Improper Output Neutralisation for Logs), aka
log forging / log injection / log splitting.

LLMs writing Java often emit::

    log.info("user logged in: " + username);
    logger.warn("query=" + req.getParameter("q"));
    LOGGER.error(String.format("failed for %s", input));
    log.info(input + " requested resource");

If ``username`` / ``input`` / ``q`` contains a CR or LF, the attacker
can forge an entire second log line ("``\\nINFO admin authenticated``")
that downstream log analytics treat as authentic. If the log sink is
HTML (Kibana, an in-house dashboard), splicing in ``<script>`` is a
stored XSS in the log viewer (CWE-79 in the secondary surface).

The safe shape is to either (a) use parameterised logging and rely on
a sink that flattens newlines, or (b) explicitly strip CR/LF/control
chars before logging, e.g.::

    String safe = username.replaceAll("[\\r\\n\\t]", "_");
    log.info("user logged in: {}", safe);

Note that parameterised logging *alone* (``log.info("x={}", x)``) is
**not** automatically safe against log forging — the formatter still
embeds ``\\n`` from ``x`` verbatim. But it is the established Java
convention and most teams pair it with a CRLF-stripping encoder, so
we treat parameterised calls with no concatenation as out of scope
and only flag the string-concatenation / String.format / formatted
shapes that are unambiguously dangerous.

What this flags
---------------
Three kinds, all on a recognised logger receiver
(``log``, ``logger``, ``LOG``, ``LOGGER``, ``slf4jLogger``, or
``Logger.getLogger(...)`` chained on the same line) followed by one
of the level methods ``trace`` / ``debug`` / ``info`` / ``warn`` /
``error`` / ``fatal``:

* **java-log-injection-concat** — argument list contains a ``+``
  outside string literals (string concatenation).
* **java-log-injection-format** — first argument is a
  ``String.format(...)`` / ``"...".formatted(...)`` /
  ``MessageFormat.format(...)`` call (the formatter has already
  produced the final string, so the placeholder mechanism that
  sinks normally CRLF-escape is bypassed).
* **java-log-injection-bare-tainted** — the only argument is a bare
  identifier that looks like a request/user value (matches one of
  ``input``, ``userInput``, ``username``, ``user``, ``req``, ``request``,
  ``param``, ``params``, ``payload``, ``body``, or any name ending
  in ``Param`` / ``Header`` / ``Cookie`` / ``Input``). Allow-listed
  names like ``message``, ``msg``, ``status``, ``count`` are not
  flagged.

What this does NOT flag
-----------------------
* Parameterised logging with literal template and no ``+``:
  ``log.info("user={}", user)`` — see note above; out of scope.
* All-literal calls: ``log.info("starting up")``.
* Calls on non-logger receivers (e.g. ``out.println(x + y)`` is a
  different problem; that's CWE-117 too but the receiver heuristic
  is intentionally narrow to keep precision high).
* Lines suffixed with ``// llm-allow:log-injection``.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Stdlib only. Exit 1 if any findings, 0 otherwise. Scans ``.java``,
``.kt`` (Kotlin uses the same SLF4J shapes), ``.md``, ``.markdown``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:log-injection"

SCAN_SUFFIXES = (".java", ".kt", ".md", ".markdown")

# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_JVM_LANGS = {"java", "kt", "kotlin"}


def _iter_jvm_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _JVM_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# String / comment scrubber. Replaces string-literal contents (including
# Java text blocks worth of ``"..."``) with spaces, and drops ``//``
# line comments. We do NOT track ``/* ... */`` across lines (line
# scanner) — false positive risk is acceptable.
# ---------------------------------------------------------------------------

def _strip(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False  # double-quoted string
    in_c = False  # char literal
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


def _arg_span(line: str, open_paren: int) -> str | None:
    """Return everything between the matched parens at the call site."""
    depth = 0
    start = open_paren + 1
    i = start
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return line[start:i]
            depth -= 1
        i += 1
    return line[start:] if start < n else None


# Logger call shape: <receiver>.<level>(
LOGGER_RECV = (
    r"(?:log|logger|LOG|LOGGER|slf4jLogger|"
    r"[A-Za-z_][A-Za-z0-9_]*Logger)"
)
LEVEL = r"(?:trace|debug|info|warn|warning|error|fatal|severe)"

LOG_CALL_RE = re.compile(
    rf"\b{LOGGER_RECV}\s*\.\s*{LEVEL}\s*\("
)

FORMAT_CALL_RE = re.compile(
    r"\bString\s*\.\s*format\s*\(|"
    r"\bMessageFormat\s*\.\s*format\s*\(|"
    r"\.\s*formatted\s*\("
)

BARE_TAINTED_NAMES = {
    "input", "userinput", "username", "user", "req", "request",
    "param", "params", "payload", "body", "data", "value", "raw",
    "querystring", "remoteuser",
}
TAINTED_SUFFIXES = ("Param", "Header", "Cookie", "Input")


def _looks_tainted_bare(arg: str) -> bool:
    a = arg.strip()
    # Strip a trailing comma (defensive).
    if a.endswith(","):
        a = a[:-1].strip()
    if not a or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", a):
        return False
    if a.lower() in BARE_TAINTED_NAMES:
        return True
    return any(a.endswith(s) for s in TAINTED_SUFFIXES)


def _has_concat(args: str) -> bool:
    """Return True if the arg list contains a top-level ``+`` operator
    (after stripping strings) — i.e., string concatenation."""
    # Re-scrub the arg list separately (caller already scrubbed the
    # outer line; this is belt-and-braces for nested literals).
    s = _strip(args)
    depth = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "+" and depth == 0:
            # Avoid ``++`` and ``+=`` (neither is concat at top level).
            prev = s[i - 1] if i > 0 else ""
            nxt = s[i + 1] if i + 1 < n else ""
            if prev != "+" and nxt not in ("+", "="):
                return True
        i += 1
    return False


def _classify(args: str) -> str | None:
    if FORMAT_CALL_RE.search(args):
        return "java-log-injection-format"
    if _has_concat(args):
        return "java-log-injection-concat"
    # Bare-tainted: only if there is no comma at top level (single arg).
    s = _strip(args)
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return None  # multi-arg => parameterised, out of scope
    if _looks_tainted_bare(args):
        return "java-log-injection-bare-tainted"
    return None


def _scan_block(block: str, base_lineno: int) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for offset, raw in enumerate(block.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        scrubbed = _strip(raw)
        for m in LOG_CALL_RE.finditer(scrubbed):
            paren = scrubbed.find("(", m.start())
            if paren < 0:
                continue
            args = _arg_span(scrubbed, paren)
            if args is None:
                continue
            kind = _classify(args)
            if kind:
                lineno = base_lineno + offset
                findings.append((lineno, kind, raw.rstrip()))
                break
    return findings


def _iter_files(roots: list[str]):
    for root in roots:
        p = Path(root)
        if p.is_file():
            yield p
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in SCAN_SUFFIXES:
                    yield child


def _scan_path(path: Path) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[tuple[int, str, str]] = []
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_jvm_blocks(text):
            findings.extend(_scan_block(body, line_offset))
    else:
        findings.extend(_scan_block(text, 0))
    return findings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_finding = False
    for path in _iter_files(argv):
        for lineno, kind, raw in _scan_path(path):
            print(f"{path}:{lineno}: {kind}: {raw.strip()}")
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
