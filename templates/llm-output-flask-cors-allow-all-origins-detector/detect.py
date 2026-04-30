#!/usr/bin/env python3
"""Detect dangerous wildcard CORS configurations in LLM-emitted Python.

Cross-Origin Resource Sharing (CORS) lets a browser running on
origin A talk to an HTTP API on origin B. The server controls
which origins are allowed via the `Access-Control-Allow-Origin`
response header. Setting that header to `*` — combined with
credentialed requests — is the canonical CSRF-amplifier: any
random page the user visits can read authenticated responses
from your API.

LLMs emit wildcard CORS configs by reflex because the shortest
"how do I fix CORS" recipe on the public internet is
`CORS(app)` (Flask-CORS) or `CORS_ORIGIN_ALLOW_ALL = True`
(django-cors-headers), both of which default to or explicitly
allow `*`.

What this flags
---------------
* `flask_cors.CORS(app)` with no `origins=` (defaults to `*`).
* `CORS(app, origins="*")` or `origins=["*"]`, including the
  per-resource `resources={...: {"origins": "*"}}` shape.
* `flask_cors.cross_origin()` with no `origins=` argument.
* `cross_origin(origins="*")` or `origins=["*"]`.
* Manual `response.headers["Access-Control-Allow-Origin"] = "*"`.
* `CORS_ORIGIN_ALLOW_ALL = True` (django-cors-headers, legacy).
* `CORS_ALLOWED_ORIGINS = ["*"]` (django-cors-headers, modern).
* `CORS_ALLOW_ALL_ORIGINS = True` (django-cors-headers, modern).
* `starlette.middleware.cors.CORSMiddleware(..., allow_origins=["*"])`
  / `app.add_middleware(CORSMiddleware, allow_origins=["*"])`
  (FastAPI / Starlette).

What this does NOT flag
-----------------------
* Explicit allowlists: `origins=["https://app.example.com"]`,
  `CORS_ALLOWED_ORIGINS = ["https://app.example.com"]`.
* Origin regexes that aren't `.*`: `origins=r"https://.*\\.example\\.com"`.
* Lines marked with the trailing suppression marker `# cors-wildcard-ok`.
* Occurrences inside `#` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python
shebang files).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Flask-CORS shapes.
RE_CORS_CALL = re.compile(r"\bCORS\s*\(")
RE_CROSS_ORIGIN_CALL = re.compile(r"\bcross_origin\s*\(")

# Django-cors-headers settings.
RE_DJANGO_ALLOW_ALL = re.compile(
    r"^\s*CORS_(?:ORIGIN_ALLOW_ALL|ALLOW_ALL_ORIGINS)\s*=\s*True\b"
)
RE_DJANGO_ALLOWED_STAR = re.compile(
    r"^\s*CORS_(?:ALLOWED_ORIGINS|ORIGIN_WHITELIST)\s*=\s*"
    r"[\[\(]\s*[\"']\*[\"']\s*[\]\)]"
)

# Manual header set.
RE_MANUAL_HEADER = re.compile(
    r"""\.headers\s*\[\s*['"]Access-Control-Allow-Origin['"]\s*\]"""
    r"""\s*=\s*['"]\*['"]"""
)

# Starlette / FastAPI CORSMiddleware shapes.
RE_CORS_MIDDLEWARE = re.compile(r"\bCORSMiddleware\b")
RE_ADD_MIDDLEWARE = re.compile(r"\.add_middleware\s*\(")

# Wildcard origins kwarg in any of the above call forms.
RE_ORIGINS_STAR = re.compile(
    r"""\borigins\s*=\s*(?:["']\*["']|[\[\(]\s*["']\*["']\s*[\]\)])"""
)
RE_ALLOW_ORIGINS_STAR = re.compile(
    r"""\ballow_origins\s*=\s*(?:["']\*["']|[\[\(]\s*["']\*["']\s*[\]\)])"""
)
RE_ORIGINS_KW = re.compile(r"\borigins\s*=")
RE_RESOURCES_STAR = re.compile(
    r"""["']origins["']\s*:\s*(?:["']\*["']|\[\s*["']\*["']\s*\])"""
)

RE_SUPPRESS = re.compile(r"#\s*cors-wildcard-ok\b")


def strip_comments_and_strings(line: str, in_triple):
    """Blank Python comment tails and string literal contents,
    preserving column positions and quote tokens. Carries
    triple-quoted string state across lines.
    """
    out = []
    i = 0
    n = len(line)
    in_str = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def extract_call_args(scrubbed: str, paren_idx: int):
    depth = 0
    for j in range(paren_idx, len(scrubbed)):
        ch = scrubbed[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return scrubbed[paren_idx + 1:j]
    return None


def has_origins_kwarg(args_text: str) -> bool:
    return bool(RE_ORIGINS_KW.search(args_text))


def scan_file(path: Path):
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        # Use the RAW line for substring matching of arg values
        # that we actually want to inspect (origins="*" is in a
        # string literal, so the scrubbed version blanks it out).
        # But we use SCRUBBED to find the structural call sites
        # and to pair `(` with `)`.

        # Flask-CORS: CORS(...).
        for m in RE_CORS_CALL.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            if RE_ORIGINS_STAR.search(raw_args):
                findings.append((path, idx, m.start() + 1,
                                 "flask-cors-origins-wildcard",
                                 raw.strip()))
            elif RE_RESOURCES_STAR.search(raw_args):
                findings.append((path, idx, m.start() + 1,
                                 "flask-cors-resources-wildcard",
                                 raw.strip()))
            elif (not has_origins_kwarg(raw_args)
                  and "resources" not in raw_args):
                # Bare CORS(app) → defaults to *. If a
                # resources={...} mapping is present, the explicit
                # per-resource origins control behavior, so don't
                # warn here.
                findings.append((path, idx, m.start() + 1,
                                 "flask-cors-default-wildcard",
                                 raw.strip()))

        # Flask-CORS: cross_origin(...).
        for m in RE_CROSS_ORIGIN_CALL.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            if RE_ORIGINS_STAR.search(raw_args):
                findings.append((path, idx, m.start() + 1,
                                 "flask-cross-origin-wildcard",
                                 raw.strip()))
            elif not has_origins_kwarg(raw_args):
                findings.append((path, idx, m.start() + 1,
                                 "flask-cross-origin-default-wildcard",
                                 raw.strip()))

        # Manual header set.
        if RE_MANUAL_HEADER.search(raw):
            findings.append((path, idx, 1,
                             "manual-allow-origin-wildcard",
                             raw.strip()))

        # Django allow-all flags.
        if RE_DJANGO_ALLOW_ALL.search(raw):
            findings.append((path, idx, 1,
                             "django-cors-allow-all",
                             raw.strip()))
        if RE_DJANGO_ALLOWED_STAR.search(raw):
            findings.append((path, idx, 1,
                             "django-cors-allowed-origins-wildcard",
                             raw.strip()))

        # Starlette / FastAPI CORSMiddleware.
        if (RE_CORS_MIDDLEWARE.search(scrub)
                and RE_ALLOW_ORIGINS_STAR.search(raw)):
            findings.append((path, idx, 1,
                             "starlette-cors-allow-origins-wildcard",
                             raw.strip()))
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def main(argv) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
