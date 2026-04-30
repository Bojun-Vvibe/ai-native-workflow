#!/usr/bin/env python3
"""Detect `requests` / `httpx` / `urllib3` HTTP calls without a timeout.

The Python `requests` library defaults to **no timeout**. A
`requests.get(url)` against an attacker-controlled host that
accepts the TCP connection but never replies will block your
worker forever, exhausting the connection pool and silently
DoSing your service. The same trap exists in `httpx` (sync
client default `5.0`s, but `httpx.get(url)` follows whatever the
caller passed) and in `urllib3.PoolManager.request`.

LLMs reliably forget the `timeout=` kwarg because the simplest
form on the public internet is `requests.get(url)`. This detector
flags any HTTP call that doesn't pass a `timeout=` and isn't
audited.

What this flags
---------------
* `requests.get | post | put | patch | delete | head | options |
  request(...)` without `timeout=`.
* A bound `Session` instance method:
  `session.get(...)` / `s.post(...)` / `client.put(...)` etc.
  with no `timeout=`. The detector recognizes the conventional
  variable names `session`, `s`, `sess`, `client`, `http`.
* `httpx.get | post | put | patch | delete | head | options |
  request(...)` without `timeout=`. Note that `httpx` *does*
  default to a 5 s timeout, but **module-level** convenience
  calls without an explicit timeout are still a code smell:
  use a `Client(timeout=...)` so the value is visible.
* `urllib3.PoolManager().request(...)` without a `timeout=`.

What this does NOT flag
-----------------------
* Any call with `timeout=` set to **any** value (including
  `None` — that's an explicit and reviewable choice; see the
  Limitations section).
* `requests.Session()` / `httpx.Client(timeout=...)` constructor
  calls — those are configuration, not the HTTP call itself.
* Calls inside `#` comments or string literals.
* Lines marked with the trailing suppression marker
  `# no-timeout-ok`.

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


HTTP_VERBS = "get|post|put|patch|delete|head|options|request"

# Module-level convenience calls.
RE_REQUESTS = re.compile(rf"\brequests\s*\.\s*({HTTP_VERBS})\s*\(")
RE_HTTPX = re.compile(rf"\bhttpx\s*\.\s*({HTTP_VERBS})\s*\(")

# urllib3 PoolManager / HTTPSConnectionPool .request / .urlopen.
RE_URLLIB3 = re.compile(
    r"\b(?:PoolManager|HTTPConnectionPool|HTTPSConnectionPool)"
    r"\s*\([^)]*\)\s*\.\s*(request|urlopen)\s*\("
)

# Bound session / client method calls. We restrict to a known
# vocabulary of variable names to keep false-positive risk low —
# `foo.get(x)` on an arbitrary `foo` is too noisy to flag.
SESSION_NAMES = r"(?:session|sess|s|client|http|api|cli)"
RE_SESSION = re.compile(
    rf"\b{SESSION_NAMES}\s*\.\s*({HTTP_VERBS})\s*\("
)

RE_TIMEOUT_KW = re.compile(r"\btimeout\s*=")
RE_SUPPRESS = re.compile(r"#\s*no-timeout-ok\b")


def strip_comments_and_strings(line: str, in_triple):
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


def has_timeout(args_text: str) -> bool:
    return bool(RE_TIMEOUT_KW.search(args_text))


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

        # requests.<verb>(...).
        for m in RE_REQUESTS.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if not has_timeout(args):
                kind = f"requests-{m.group(1)}-no-timeout"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))

        # httpx.<verb>(...).
        for m in RE_HTTPX.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if not has_timeout(args):
                kind = f"httpx-{m.group(1)}-no-timeout"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))

        # urllib3 PoolManager().request(...).
        for m in RE_URLLIB3.finditer(scrub):
            paren = scrub.find("(", m.end() - 1)
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if not has_timeout(args):
                kind = f"urllib3-{m.group(1)}-no-timeout"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))

        # session/client.<verb>(...).
        for m in RE_SESSION.finditer(scrub):
            # Skip if already matched by requests./httpx. — those
            # have a leading word boundary on the module name and
            # SESSION_NAMES like "s" could match against
            # "requests.get" if regex order shifted. Use start
            # column to dedupe.
            start_col = m.start()
            already = any(
                f[2] == start_col + 1 for f in findings
                if f[1] == idx
            )
            if already:
                continue
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if not has_timeout(args):
                kind = f"session-{m.group(1)}-no-timeout"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))
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
