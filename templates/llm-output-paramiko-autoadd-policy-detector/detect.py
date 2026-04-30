#!/usr/bin/env python3
"""Detect Paramiko / Fabric SSH client code that disables host-key verification.

The disastrous shapes this catches:

    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.set_missing_host_key_policy(AutoAddPolicy)        # the class itself
    client.load_system_host_keys()  # ... then ... AutoAddPolicy

These bypass the entire SSH host-key trust model: the first time the script
connects, it silently accepts whatever public key the remote presents, which
is exactly what an SSH MITM attacker hands over. CWE-322 / CWE-295 in SSH
form. The Paramiko docs explicitly say AutoAddPolicy "is not suitable for
production-use".

What this flags
---------------
* `set_missing_host_key_policy(<anything>AutoAddPolicy<anything>)`
* `set_missing_host_key_policy(<anything>WarningPolicy<anything>)`
* Direct construction of `paramiko.AutoAddPolicy()` / `AutoAddPolicy()` /
  `paramiko.client.AutoAddPolicy()` even outside `set_missing_host_key_policy`
  (LLMs sometimes assign it to a variable first).
* Fabric `Connection(... connect_kwargs={"... AutoAddPolicy ..."})` shape via
  the bare AutoAddPolicy detection above.

What this does NOT flag
-----------------------
* `RejectPolicy` (the safe default)
* String literals or comments mentioning the class name
* Lines marked with a trailing `# ssh-policy-ok` comment (e.g. throwaway
  ephemeral test container that is destroyed after each run)

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Pure single-pass line scanner — does not import `ast` so it stays
robust against syntactically broken snippets.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SET_POLICY_AUTOADD = re.compile(
    r"\.set_missing_host_key_policy\s*\([^)]*\bAutoAddPolicy\b"
)
RE_SET_POLICY_WARNING = re.compile(
    r"\.set_missing_host_key_policy\s*\([^)]*\bWarningPolicy\b"
)
RE_BARE_AUTOADD = re.compile(r"\bAutoAddPolicy\s*\(")
RE_BARE_WARNING = re.compile(r"\bWarningPolicy\s*\(")
RE_SUPPRESS = re.compile(r"#\s*ssh-policy-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None) -> tuple[str, str | None]:
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
                    out.append("   ")
                    i += 3
                    continue
                in_str = ch
                out.append(" ")
                i += 1
                continue
            out.append(ch)
            i += 1
        else:
            if len(in_str) == 3:
                if line[i:i + 3] == in_str:
                    in_str = None
                    out.append("   ")
                    i += 3
                    continue
                out.append(" ")
                i += 1
            else:
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                    out.append(" ")
                    i += 1
                    continue
                out.append(" ")
                i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            _, in_triple = strip_comments_and_strings(raw, in_triple)
            continue
        stripped, in_triple = strip_comments_and_strings(raw, in_triple)
        for rx, label in (
            (RE_SET_POLICY_AUTOADD,
             "ssh-host-key-bypass: set_missing_host_key_policy(AutoAddPolicy)"),
            (RE_SET_POLICY_WARNING,
             "ssh-host-key-bypass: set_missing_host_key_policy(WarningPolicy)"),
        ):
            if rx.search(stripped):
                findings.append((lineno, label, raw.rstrip()))
                break
        else:
            # Only flag bare construction if we did not already flag a
            # set_missing_host_key_policy on the same line (avoids double
            # reporting).
            if RE_BARE_AUTOADD.search(stripped):
                findings.append(
                    (lineno,
                     "ssh-host-key-bypass: AutoAddPolicy() instantiated",
                     raw.rstrip())
                )
            elif RE_BARE_WARNING.search(stripped):
                findings.append(
                    (lineno,
                     "ssh-host-key-bypass: WarningPolicy() instantiated",
                     raw.rstrip())
                )
    return findings


def iter_targets(args: list[str]):
    for a in args:
        p = Path(a)
        if p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    any_finding = False
    for path in iter_targets(argv[1:]):
        for lineno, label, raw in scan_file(path):
            any_finding = True
            print(f"{path}:{lineno}: {label} :: {raw.strip()}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
