#!/usr/bin/env python3
"""Detect Flask apps shipped with `debug=True`.

Flask's debug mode wires the Werkzeug interactive debugger into
the WSGI stack. When an unhandled exception fires, the debugger
serves an HTML page that lets anyone with a browser execute
arbitrary Python in the app's process — pinned only by a PIN
that is derived from predictable host facts and has been
bypassed multiple times in the wild. Running a debug-mode Flask
app on a reachable interface is equivalent to publishing a
remote code execution endpoint.

LLMs love `app.run(debug=True)` because it's the canonical
"hello world" snippet in every Flask tutorial. The same
shape leaks into Dockerfiles (`FLASK_DEBUG=1` /
`FLASK_ENV=development`) and into `os.environ` mutations inside
`if __name__ == "__main__":` blocks.

What this flags
---------------
* `app.run(..., debug=True)` and `<anything>.run(..., debug=True)`
  on a name plausibly holding a Flask app
* `Flask.run(..., debug=True)`
* `app.config["DEBUG"] = True` / `app.config.update(DEBUG=True)`
* `os.environ["FLASK_DEBUG"] = "1"` / `"true"` / `"True"`
* `os.environ["FLASK_ENV"] = "development"`
* In Dockerfile/`.env`-style files: `FLASK_DEBUG=1` /
  `FLASK_DEBUG=true` / `FLASK_ENV=development` as a top-level
  assignment (anywhere on a line that isn't a `#` comment).

What this does NOT flag
-----------------------
* `app.run(debug=False)` or `app.run()` (default is False).
* `app.config["DEBUG"] = False`.
* `FLASK_DEBUG=0` / `FLASK_ENV=production`.
* Lines marked with a trailing `# flask-debug-ok` comment.
* Occurrences inside `#` comments or string literals in `.py`
  files (the scanner masks both before matching).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python
shebang files), Dockerfiles, and `.env` / `.envrc` files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# .run(... debug=True ...) — first the call detection, then check kwargs.
RE_RUN_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*run\s*\(")
RE_DEBUG_TRUE_KW = re.compile(r"\bdebug\s*=\s*True\b")

# app.config["DEBUG"] = True / app.config['DEBUG'] = True
RE_CONFIG_ASSIGN = re.compile(
    r"""\.\s*config\s*\[\s*['"]DEBUG['"]\s*\]\s*=\s*True\b"""
)
# app.config.update(DEBUG=True) / app.config.update(debug=True)? Flask
# normalises uppercase only — match uppercase form.
RE_CONFIG_UPDATE = re.compile(
    r"\.\s*config\s*\.\s*update\s*\([^)]*\bDEBUG\s*=\s*True\b"
)

# os.environ["FLASK_DEBUG"] = "1" / "true" / "True"
RE_ENV_FLASK_DEBUG = re.compile(
    r"""os\s*\.\s*environ\s*\[\s*['"]FLASK_DEBUG['"]\s*\]\s*=\s*"""
    r"""['"](1|true|True|TRUE|yes|on)['"]"""
)
# os.environ["FLASK_ENV"] = "development"
RE_ENV_FLASK_ENV_DEV = re.compile(
    r"""os\s*\.\s*environ\s*\[\s*['"]FLASK_ENV['"]\s*\]\s*=\s*"""
    r"""['"]development['"]"""
)

# Plain assignment in Dockerfile / .env style.
# Matches FLASK_DEBUG=1|true|yes|on, FLASK_ENV=development.
# We allow leading ENV / export keywords so this works for both.
RE_DOTENV_FLASK_DEBUG = re.compile(
    r"^\s*(?:ENV\s+|export\s+)?FLASK_DEBUG\s*=\s*['\"]?(1|true|True|TRUE|yes|on)\b"
)
RE_DOTENV_FLASK_ENV = re.compile(
    r"^\s*(?:ENV\s+|export\s+)?FLASK_ENV\s*=\s*['\"]?development\b"
)

RE_SUPPRESS = re.compile(r"#\s*flask-debug-ok\b")


# Names we'll trust as "looks like a Flask app" for the .run() check.
# We're permissive: anything that is plausibly a WSGI/Flask handle.
APP_NAME_HINT = re.compile(
    r"^(app|application|server|flask_app|wsgi|api|web|create_app|Flask)$"
)


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None, str]:
    """Return (scrub_full, in_triple_after, code_only).

    `scrub_full` masks both comments and string literal contents,
    preserving column positions. `code_only` masks only Python
    comments and any portion of the line that begins inside a
    triple-quoted string — short single-line string contents are
    preserved so we can match patterns like
    `os.environ["FLASK_DEBUG"] = "1"` that depend on string
    literal text.
    """
    out: list[str] = []
    code: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    started_in_triple = in_triple is not None
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                code.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    code.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                code.append(ch)
                i += 1
                continue
            out.append(ch)
            code.append(ch)
            i += 1
            continue
        # inside a string
        is_triple = len(in_str) == 3
        if not is_triple and ch == "\\" and i + 1 < n:
            out.append("  ")
            # preserve raw chars in code_only for single-line
            # strings (so "DEBUG" survives)
            code.append(line[i:i + 2])
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            code.append(in_str)
            i += len(in_str)
            in_str = None
            started_in_triple = False
            continue
        out.append(" ")
        # If we started this line inside a triple-quoted string,
        # blank the chars; if it's a single-line string we
        # discovered on this line, preserve them.
        if is_triple or started_in_triple:
            code.append(" ")
        else:
            code.append(ch)
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str, "".join(code)


def extract_call_args(scrubbed: str, paren_idx: int) -> str | None:
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


def scan_python(path: Path, text: str) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple, code_only = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        # <name>.run(..., debug=True) — use scrub (call shape, kwargs)
        for m in RE_RUN_CALL.finditer(scrub):
            name = m.group(1)
            if not APP_NAME_HINT.match(name):
                continue
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if RE_DEBUG_TRUE_KW.search(args):
                findings.append((path, idx, m.start() + 1,
                                 f"flask-{name}-run-debug-true", raw.strip()))

        # app.config["DEBUG"] = True  — needs string contents
        for m in RE_CONFIG_ASSIGN.finditer(code_only):
            findings.append((path, idx, m.start() + 1,
                             "flask-config-debug-true", raw.strip()))

        # app.config.update(DEBUG=True)
        for m in RE_CONFIG_UPDATE.finditer(scrub):
            findings.append((path, idx, m.start() + 1,
                             "flask-config-update-debug-true", raw.strip()))

        # os.environ["FLASK_DEBUG"] = "1"
        for m in RE_ENV_FLASK_DEBUG.finditer(code_only):
            findings.append((path, idx, m.start() + 1,
                             "flask-env-flask-debug-true", raw.strip()))

        # os.environ["FLASK_ENV"] = "development"
        for m in RE_ENV_FLASK_ENV_DEV.finditer(code_only):
            findings.append((path, idx, m.start() + 1,
                             "flask-env-flask-env-development", raw.strip()))
    return findings


def scan_dotenv(path: Path, text: str) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        if RE_SUPPRESS.search(raw):
            continue
        m = RE_DOTENV_FLASK_DEBUG.match(raw)
        if m:
            findings.append((path, idx, 1, "dotenv-flask-debug-true", raw.strip()))
            continue
        m = RE_DOTENV_FLASK_ENV.match(raw)
        if m:
            findings.append((path, idx, 1, "dotenv-flask-env-development", raw.strip()))
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


def is_envish_file(path: Path) -> bool:
    name = path.name
    if name == "Dockerfile" or name.startswith("Dockerfile."):
        return True
    if name in (".env", ".envrc"):
        return True
    if name.startswith(".env."):
        return True
    if path.suffix == ".env":
        return True
    return False


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if not sub.is_file():
                    continue
                if is_python_file(sub) or is_envish_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if is_python_file(path):
        return scan_python(path, text)
    if is_envish_file(path):
        return scan_dotenv(path, text)
    return []


def main(argv: list[str]) -> int:
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
