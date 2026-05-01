#!/usr/bin/env python3
"""
llm-output-bash-curl-pipe-shell-detector

Flags shell scripts that fetch a remote payload with `curl` or `wget`
and pipe it directly into a shell interpreter -- the classic
`curl ... | sh` / `wget -O- ... | bash` install pattern.

Why it's bad:
  - The payload is executed at fetch time with no integrity check.
  - A network attacker (or a compromised mirror, or even a server-side
    User-Agent sniff) can ship different bytes to your machine than
    they ship to a verifier.
  - The script you actually ran is never written to disk, so audit /
    incident response cannot reconstruct it.

This maps to:
  - CWE-494: Download of Code Without Integrity Check
  - CWE-78: OS Command Injection (when the URL contains user input)

LLMs reach for this pattern because nearly every "getting started"
README on the open web shows it. We catch it.

Heuristic (stdlib only):

  For each logical line (joining backslash continuations, skipping `#` lines):
    1. Find a fetcher invocation:
         - curl   ... (any flags)
         - wget   ... (any flags)
         - fetch  ... (BSD)
       that is reading from an http(s)/ftp URL.
    2. Look for a pipe (`|` not inside a quoted string) followed by
       one of: sh, bash, zsh, ksh, dash, ash, csh, tcsh, fish, python,
       python3, perl, ruby, node, php, lua -- optionally with flags.
    3. If both conditions hold, emit a finding.

  Also flag the equivalent process-substitution form
  `bash <(curl ... )` and `sh -c "$(curl ...)"`.

We do NOT flag:
  - `curl -o file.tgz https://... && sha256sum -c file.tgz.sha256`
  - `curl ... > file && bash file`  (writes to disk, auditable)
  - Pipes that don't end in an interpreter (e.g. `curl ... | jq .`)

Stdlib only. Reads files passed on argv (or recurses into dirs and
picks `*.sh`, `*.bash`, `Makefile`, `Dockerfile`). Exit 0 = no
findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

INTERPRETERS = (
    "sh", "bash", "zsh", "ksh", "dash", "ash", "csh", "tcsh", "fish",
    "python", "python3", "python2", "perl", "ruby", "node", "php", "lua",
)
_INTERP_ALT = "|".join(INTERPRETERS)

# Fetchers that pull bytes over the network.
_FETCHER_RE = re.compile(
    r"\b(curl|wget|fetch)\b[^|<]*?(?:https?|ftp)://",
    re.IGNORECASE,
)

# `... | <interp> [flags...]` where interp is at the END or followed by a
# word break / pipe / redir / `&&` / `||` / `;`.
_PIPE_INTERP_RE = re.compile(
    r"\|\s*(?:/usr/bin/env\s+)?(?:" + _INTERP_ALT + r")(?:\s|$|;|&|\||>)",
)

# `bash <(curl ...)` / `sh <(wget ...)`
_PROCSUB_RE = re.compile(
    r"\b(?:" + _INTERP_ALT + r")\b\s+(?:-\S+\s+)*<\(\s*(?:curl|wget|fetch)\b[^)]*?(?:https?|ftp)://",
    re.IGNORECASE,
)

# `sh -c "$(curl ...)"` / `bash -c "$(wget ...)"` -- command substitution
# fed straight into an interpreter via -c.
_DASHC_CMDSUB_RE = re.compile(
    r"\b(?:" + _INTERP_ALT + r")\b\s+-c\s+[\"']?\$\(\s*(?:curl|wget|fetch)\b[^)]*?(?:https?|ftp)://",
    re.IGNORECASE,
)


def _logical_lines(text: str) -> Iterable[Tuple[int, str]]:
    raw = text.splitlines()
    i = 0
    n = len(raw)
    while i < n:
        start_lineno = i + 1
        line = raw[i]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        joined_parts = [line.rstrip()]
        while joined_parts[-1].endswith("\\") and i + 1 < n:
            joined_parts[-1] = joined_parts[-1][:-1]
            i += 1
            joined_parts.append(raw[i].rstrip())
        i += 1
        yield start_lineno, " ".join(p.strip() for p in joined_parts).strip()


def _is_curl_pipe_interp(line: str) -> bool:
    """Pipe form: a fetcher must appear, and a pipe-to-interpreter must
    appear *after* the fetcher position."""
    fm = _FETCHER_RE.search(line)
    if not fm:
        return False
    after = line[fm.end():]
    return bool(_PIPE_INTERP_RE.search(after))


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, logical in _logical_lines(text):
        why = None
        if _is_curl_pipe_interp(logical):
            why = "curl|wget piped directly into a shell/interpreter"
        elif _PROCSUB_RE.search(logical):
            why = "interpreter reading process-substituted curl/wget output"
        elif _DASHC_CMDSUB_RE.search(logical):
            why = "interpreter -c with command-substituted curl/wget output"
        if why:
            findings.append(
                f"{path}:{lineno}: {why} "
                f"(CWE-494: download of code without integrity check)"
            )
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if (
                        f.endswith(".sh")
                        or f.endswith(".bash")
                        or f == "Makefile"
                        or f == "Dockerfile"
                        or f.endswith(".Dockerfile")
                    ):
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
