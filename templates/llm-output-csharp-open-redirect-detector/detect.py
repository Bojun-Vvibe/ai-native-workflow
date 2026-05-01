#!/usr/bin/env python3
"""Detect open-redirect (CWE-601) sinks in LLM-emitted C# / ASP.NET code.

LLMs writing ASP.NET MVC / Web API controllers frequently emit::

    return Redirect(returnUrl);
    return RedirectPermanent(Request.Query["next"]);
    Response.Redirect(model.Url);
    return new RedirectResult(target);

…where the URL came directly from a request parameter, route value,
form field, header, cookie, or query string. When the value is not
constrained to the local site, an attacker can send the user to an
arbitrary external host (phishing, OAuth code theft, token leak via
referrer, etc.). The framework-supplied ``LocalRedirect`` /
``IsLocalUrl`` family explicitly reject absolute / scheme-bearing URLs
and are the documented mitigation.

What this flags
---------------
A line in a ``.cs`` file that calls a redirect sink with what looks
like a tainted argument and the *same file* never opts in to any of
the recognised mitigations::

    LocalRedirect(...)
    LocalRedirectPermanent(...)
    Url.IsLocalUrl(...)
    new LocalRedirectResult(...)

Tainted argument heuristics (case-insensitive substring on the raw
argument text):

    Request., HttpContext.Request, Query[, Form[, Headers[,
    RouteData, returnUrl, redirectUrl, next, target,
    Model., model., dto., input.

What this does NOT flag
-----------------------
* String literals: ``Redirect("/home")`` — no tainted token.
* Files that contain any of the mitigation tokens above.
* Lines suffixed with ``// redirect-ok``.
* Sinks inside ``//`` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// redirect-ok"

# Match a redirect call and capture the arg list up to the matching ).
# We use a non-greedy + balanced-ish heuristic: stop at the first ) that
# is not inside nested parens. Good enough for one-line LLM output.
RE_SINK = re.compile(
    r"\b(?:return\s+)?"
    r"(Redirect|RedirectPermanent|RedirectPreserveMethod|"
    r"RedirectPermanentPreserveMethod|RedirectToAction|"
    r"Response\s*\.\s*Redirect|"
    r"new\s+RedirectResult)\s*\("
)

RE_NEW_REDIRECT_RESULT = re.compile(r"\bnew\s+RedirectResult\b")

TAINT_TOKENS = (
    "request.",
    "httpcontext.request",
    "query[",
    "form[",
    "headers[",
    "cookies[",
    "routedata",
    "returnurl",
    "redirecturl",
    "redirect_uri",
    "next_url",
    "model.",
    "dto.",
    "input.",
    "viewbag.",
    "tempdata[",
    " next",
    "(next",
    ",next",
    " target",
    "(target",
    ",target",
    " url",
    "(url",
    ",url",
)

RE_MITIGATIONS = re.compile(
    r"(?:"
    r"\bLocalRedirect(?:Permanent|PreserveMethod)?\s*\(|"
    r"\bnew\s+LocalRedirectResult\b|"
    r"\bUrl\s*\.\s*IsLocalUrl\s*\("
    r")"
)


def _strip_strings_and_comments(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_v = False
    in_c = False
    while i < n:
        ch = line[i]
        if in_v:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    out.append("  ")
                    i += 2
                    continue
                in_v = False
                out.append('"')
            else:
                out.append(" ")
        elif in_s:
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
            if ch == "@" and i + 1 < n and line[i + 1] == '"':
                in_v = True
                out.append(' "')
                i += 2
                continue
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


def _extract_arg(stripped: str, start: int) -> str:
    """Return text inside the matching parens beginning at index `start`
    (which points at the '(' after the sink name)."""
    depth = 0
    out: list[str] = []
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return "".join(out)
        if depth >= 1:
            out.append(ch)
    return "".join(out)


def _file_has_mitigations(text: str) -> bool:
    return RE_MITIGATIONS.search(text) is not None


def _looks_tainted(arg: str) -> bool:
    low = arg.lower()
    return any(tok in low for tok in TAINT_TOKENS)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    if _file_has_mitigations(text):
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        stripped = _strip_strings_and_comments(raw)
        m = RE_SINK.search(stripped)
        if not m:
            continue
        # find the '(' that opens the sink call
        paren_idx = stripped.find("(", m.end() - 1)
        if paren_idx < 0:
            continue
        arg = _extract_arg(stripped, paren_idx)
        if not arg.strip():
            continue
        if not _looks_tainted(arg):
            continue
        sink = m.group(1).replace(" ", "").replace("\t", "")
        kind = f"openredirect-{sink}"
        findings.append((path, lineno, kind, raw.rstrip()))
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.cs")):
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
