#!/usr/bin/env python3
"""
llm-output-python-jinja2-autoescape-false-detector

Flags Python code that constructs a Jinja2 rendering surface with
HTML autoescaping disabled. This is the canonical CWE-79 (XSS)
shape that LLMs love to emit when asked "set up Jinja for my
Flask app": the model copies the *library default* of
`autoescape=False` into the explicit constructor call, which is a
silent foot-gun the moment any template ever interpolates user
input into HTML.

What this flags
---------------
* `jinja2.Environment(...)` / `Environment(...)` with
  `autoescape=False`, `autoescape=0`, or no `autoescape=` keyword
  at all when the call site clearly targets HTML
  (`FileSystemLoader`, `PackageLoader`, `.html`, `.htm` strings
  in the same expression).
* `jinja2.Template(<source>, autoescape=False)`.
* `Environment(..., autoescape=select_autoescape([]))` — empty
  list means "never autoescape anything".
* `Environment(..., autoescape=lambda *_: False)` and the
  equivalent `def` returning a constant `False`.

What this does NOT flag
-----------------------
* `Environment(autoescape=True)` (correct).
* `Environment(autoescape=select_autoescape(['html', 'htm']))`
  (the standard recommended idiom).
* `Environment(autoescape=select_autoescape(default_for_string=True))`.
* Files that have no `jinja2` reference at all — the bare word
  `Environment` could be anything, so we require co-location.

Stdlib only. Reads files passed on argv (or recurses into
directories). Exit 0 = no findings, 1 = at least one finding,
2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Anchor: the file mentions jinja2 somewhere. Prevents false positives
# on unrelated `Environment` / `Template` symbols (Django, SQLAlchemy,
# etc.).
_JINJA_PRESENT_RE = re.compile(r"\bjinja2\b")

# Captures the entire call's argument list for an Environment(...) or
# jinja2.Environment(...) call. Group 1 = argstring.
_ENV_CALL_RE = re.compile(
    r"\b(?:jinja2\s*\.\s*)?Environment\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)

# Same for Template(...) — only meaningful when the file references jinja2.
_TPL_CALL_RE = re.compile(
    r"\b(?:jinja2\s*\.\s*)?Template\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)

# Inside a call's argstring, find autoescape=. We extract the value
# manually with paren/bracket balancing because the value is often
# select_autoescape([...]) which itself contains commas.
_AE_KW_RE = re.compile(r"\bautoescape\s*=\s*")


def _extract_kwarg_value(args: str, start: int) -> str:
    """Given args[start:] positioned right after `autoescape=`, return
    the value text up to the next top-level comma or end-of-string."""
    depth = 0
    in_str = None
    out: List[str] = []
    i = start
    n = len(args)
    while i < n:
        c = args[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(args[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in "\"'":
            in_str = c
            out.append(c)
            i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif c == "," and depth == 0:
            break
        out.append(c)
        i += 1
    return "".join(out).strip()

# Hints that the Environment is for HTML rendering. We use these to flag
# *missing* autoescape= as well, since jinja2's library default is False.
_HTML_HINT_RE = re.compile(
    r"""(?x)
    (?:
        FileSystemLoader\(
      | PackageLoader\(
      | DictLoader\(
      | ChoiceLoader\(
      | ['"][^'"]*\.html?['"]
      | ['"][^'"]*\.j2['"]
      | ['"][^'"]*\.jinja['"]
    )
    """
)

# Values that mean "autoescape is OFF".
_FALSE_AE_RE = re.compile(
    r"""(?x)
    ^\s*
    (?:
        False
      | 0
      | None
      | select_autoescape\s*\(\s*\)             # explicit empty
      | select_autoescape\s*\(\s*\[\s*\]\s*\)   # select_autoescape([])
      | lambda\b[^:]*:\s*False
    )
    \s*$
    """
)

# Values that are clearly safe.
_SAFE_AE_RE = re.compile(
    r"""(?x)
    \b(?:
        True
      | select_autoescape\s*\(\s*[^)]*(?:html|htm|xml|j2|jinja|default_for_string|default\s*=\s*True)[^)]*\)
    )
    """
)


def _line_no(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _JINJA_PRESENT_RE.search(text):
        return findings

    # Environment(...)
    for m in _ENV_CALL_RE.finditer(text):
        args = m.group(1)
        ae = _AE_KW_RE.search(args)
        is_html = bool(_HTML_HINT_RE.search(args)) or _looks_html_context(text, m.start())
        if ae is not None:
            val = _extract_kwarg_value(args, ae.end())
            if _FALSE_AE_RE.match(val):
                findings.append(
                    f"{path}:{_line_no(text, m.start())}: jinja2.Environment "
                    f"with autoescape disabled (CWE-79 XSS): autoescape={val[:60]!s}"
                )
            elif _SAFE_AE_RE.search(val):
                continue
            else:
                # Unknown value; only flag when html context is obvious.
                if is_html:
                    findings.append(
                        f"{path}:{_line_no(text, m.start())}: jinja2.Environment "
                        f"with non-allowlist autoescape= in HTML context "
                        f"(CWE-79 XSS): autoescape={val[:60]!s}"
                    )
        else:
            # autoescape= absent. Jinja2 default is False. Only flag if we
            # can see an HTML hint in the call or context.
            if is_html:
                findings.append(
                    f"{path}:{_line_no(text, m.start())}: jinja2.Environment "
                    f"in HTML context without autoescape= "
                    f"(library default is False, CWE-79 XSS)"
                )

    # Template(...) — only flag when autoescape=<falsey> is explicit.
    for m in _TPL_CALL_RE.finditer(text):
        args = m.group(1)
        ae = _AE_KW_RE.search(args)
        if ae is None:
            continue
        val = _extract_kwarg_value(args, ae.end())
        if _FALSE_AE_RE.match(val):
            findings.append(
                f"{path}:{_line_no(text, m.start())}: jinja2.Template "
                f"with autoescape disabled (CWE-79 XSS): autoescape={val[:60]!s}"
            )

    return findings


def _looks_html_context(text: str, off: int) -> bool:
    """Look at the 200 chars before the call site for HTML cues."""
    window = text[max(0, off - 200) : off]
    return bool(_HTML_HINT_RE.search(window))


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(".py") or f.endswith(".py.txt"):
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
