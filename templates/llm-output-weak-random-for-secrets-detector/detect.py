#!/usr/bin/env python3
"""Detect Python's `random` module being used for security-sensitive values.

The stdlib `random` module is a Mersenne Twister PRNG seeded
from a small amount of state — its output is **predictable**
once a few hundred outputs are observed. Using it to mint
session tokens, password-reset codes, API keys, OAuth state
parameters, CSRF tokens, salts, or initialization vectors is a
classic LLM-emitted footgun: the snippet "looks random" but is
trivially forgeable.

The hardened path is `secrets` (`secrets.token_hex`,
`secrets.token_urlsafe`, `secrets.token_bytes`,
`secrets.choice`, `secrets.randbelow`) or
`os.urandom(...)` for raw bytes.

What this flags
---------------
* `random.<call>(...)` where `<call>` is one of `random`,
  `randint`, `randrange`, `choice`, `choices`, `sample`,
  `shuffle`, `getrandbits`, `uniform`, `randbytes` — when the
  same logical line (or the surrounding 3 lines) mentions a
  security-sensitive identifier (`token`, `secret`, `password`,
  `passwd`, `apikey`, `api_key`, `nonce`, `salt`, `iv`,
  `session`, `csrf`, `otp`, `mfa`, `reset_code`, `auth`,
  `signature`, `cookie`).
* Bare `Random()` / `SystemRandom()` confusion: a call to
  `random.Random()` (the *non-CSPRNG* class) feeding any of
  the above security identifiers.

What this does NOT flag
-----------------------
* `secrets.*`, `os.urandom`, `random.SystemRandom().*`
* Pure simulation / Monte-Carlo / shuffling decks of cards —
  i.e. when the line does not mention a security identifier.
* Lines marked with a trailing `# weak-random-ok` comment.
* Occurrences inside `#` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SENSITIVE = (
    r"token|secret|password|passwd|apikey|api[_-]?key|nonce|salt"
    r"|iv\b|session|csrf|xsrf|otp|mfa|reset[_-]?code|auth"
    r"|signature|sign(?:ing)?[_-]?key|cookie|jwt|bearer"
)
RE_SENSITIVE = re.compile(SENSITIVE, re.IGNORECASE)

WEAK_CALLS = (
    "random", "randint", "randrange", "choice", "choices",
    "sample", "shuffle", "getrandbits", "uniform", "randbytes",
)
RE_WEAK_CALL = re.compile(
    r"\brandom\s*\.\s*(" + "|".join(WEAK_CALLS) + r")\s*\("
)
RE_WEAK_RANDOM_CLASS = re.compile(
    r"\brandom\s*\.\s*Random\s*\(\s*\)"
)
# Bare-imported call surfaces, e.g. `from random import randint`
# then `randint(...)`.
RE_BARE_CALL = re.compile(
    r"(?<![\w.])(" + "|".join(WEAK_CALLS) + r")\s*\("
)
RE_FROM_RANDOM_IMPORT = re.compile(
    r"^\s*from\s+random\s+import\s+(.+)$"
)

RE_SUPPRESS = re.compile(r"#\s*weak-random-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
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


def collect_bare_imports(text: str) -> set[str]:
    """Return weak-call names that have been bare-imported from
    the `random` module, e.g. `from random import choice, randint`.
    """
    names: set[str] = set()
    for raw in text.splitlines():
        m = RE_FROM_RANDOM_IMPORT.match(raw)
        if not m:
            continue
        for token in re.split(r"[,\s]+", m.group(1).strip()):
            tok = token.split(" as ")[0].strip()
            if tok in WEAK_CALLS:
                names.add(tok)
    return names


def context_window(scrubbed_lines: list[str], idx: int, radius: int = 2) -> str:
    lo = max(0, idx - radius)
    hi = min(len(scrubbed_lines), idx + radius + 1)
    return "\n".join(scrubbed_lines[lo:hi])


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    bare_names = collect_bare_imports(text)
    raw_lines = text.splitlines()
    scrubbed: list[str] = []
    in_triple: str | None = None
    for raw in raw_lines:
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        scrubbed.append(scrub)

    for idx, raw in enumerate(raw_lines):
        scrub = scrubbed[idx]
        if RE_SUPPRESS.search(raw):
            continue
        ctx = context_window(scrubbed, idx, radius=2)
        if not RE_SENSITIVE.search(ctx):
            continue
        for m in RE_WEAK_CALL.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1,
                 f"weak-random-{m.group(1)}-for-secret", raw.strip())
            )
        for m in RE_WEAK_RANDOM_CLASS.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1,
                 "weak-random-Random-class-for-secret", raw.strip())
            )
        if bare_names:
            for m in RE_BARE_CALL.finditer(scrub):
                if m.group(1) not in bare_names:
                    continue
                # Avoid double-counting `random.choice(`.
                if scrub[max(0, m.start() - 7):m.start()].rstrip().endswith("random."):
                    continue
                findings.append(
                    (path, idx + 1, m.start() + 1,
                     f"weak-random-bare-{m.group(1)}-for-secret",
                     raw.strip())
                )
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


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
                    yield sub
        elif p.is_file():
            yield p


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
