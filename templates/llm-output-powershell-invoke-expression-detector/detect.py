#!/usr/bin/env python3
"""Detect PowerShell `Invoke-Expression` (and `iex`) on dynamic strings.

`Invoke-Expression STRING` in PowerShell takes its string argument and
re-parses it as a PowerShell script in the current scope. Any variable,
subexpression, pipeline output, or user-controlled fragment that flows
into `Invoke-Expression` is a code-injection sink with the same blast
radius as `system($USER_INPUT)`.

The alias `iex` is a near-universal LLM tell — `iex (irm http://...)`
is the canonical drive-by-download pattern.

LLM-emitted PowerShell frequently reaches for `Invoke-Expression` to
"run a command stored in a variable." That is almost always wrong;
the safe alternatives are:

* `& $cmd $arg1 $arg2 ...`        — call operator with arg list
* `& { ...literal scriptblock... }` — scriptblock invocation
* `Start-Process -FilePath ... -ArgumentList ...`
* never `Invoke-Expression $cmd` / `iex $cmd`

What this flags
---------------
A bareword `Invoke-Expression` or `iex` token at command position.
"Command position" means: start-of-line (after optional whitespace),
or after `;`, `|`, `&&`, `||`, `(`, `{`, or `=` (assignment).

* `Invoke-Expression $cmd`               — variable, UNSAFE
* `iex $cmd`                              — alias, same thing, UNSAFE
* `iex "Get-Process $name"`               — interpolated string, UNSAFE
* `iex (Invoke-RestMethod $url)`         — pipeline into iex, UNSAFE
* `Invoke-Expression 'Get-Date'`         — literal-string iex,
                                            still flagged (low risk
                                            but rarely justified)
* `iex -Command $cmd`                     — explicit -Command param

Out of scope (deliberately)
---------------------------
* `Invoke-Command`, `Invoke-WebRequest`, `Invoke-RestMethod` — these
  are different cmdlets, not flagged. Only `Invoke-Expression` and
  its `iex` alias.
* `[scriptblock]::Create($s)` followed by `& $sb` — a separate sink
  worth its own detector; not flagged here.
* `&` (call operator) on a variable is dangerous in different ways
  but is the recommended replacement for `iex` and not flagged.

Suppress an audited line with a trailing `# iex-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.ps1, *.psm1, *.psd1.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match a bareword `Invoke-Expression` or `iex` at command position.
# Command position: start-of-line (after optional whitespace), or
# after `;`, `|`, `&`, `(`, `{`, or `=`. Followed by whitespace and
# at least one more non-whitespace char (the argument). Case-insensitive
# because PowerShell identifiers are case-insensitive.
RE_IEX = re.compile(
    r"(?:^|(?<=[;|&({=]))"
    r"\s*\b(Invoke-Expression|iex)\b\s+(\S)",
    re.IGNORECASE,
)

# Suppression marker: `# iex-ok` on the line.
RE_SUPPRESS = re.compile(r"#\s*iex-ok\b", re.IGNORECASE)


def strip_comments_and_strings(line: str) -> str:
    """Blank out '...' / "..." string contents and `#` line comments
    while preserving column positions. PowerShell's `<# ... #>` block
    comments span multiple lines and are NOT handled here (they are
    rare in LLM output and would require a multi-line state machine).
    Single-line `#` comments are handled.

    Note: PowerShell here-strings (`@" ... "@` / `@' ... '@`) are
    multi-line and NOT separately tracked; this scrubber operates one
    line at a time. False-positives inside here-string bodies are
    treated as findings worth a human glance — that's the conservative
    posture for a security-focused detector.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                # `#` is a line comment in PowerShell at any position
                # (unlike shell). Conservatively treat any `#` as
                # comment start when not inside a string.
                out.append(" " * (n - i))
                break
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "`" and in_s == '"' and i + 1 < n:
            # PowerShell uses backtick as escape inside double quotes
            out.append("  ")
            i += 2
            continue
        if ch == in_s:
            # PowerShell doubles the quote char to escape: '' or ""
            if i + 1 < n and line[i + 1] == in_s:
                out.append("  ")
                i += 2
                continue
            in_s = None
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_powershell_file(path: Path) -> bool:
    return path.suffix.lower() in (".ps1", ".psm1", ".psd1")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)
        for m in RE_IEX.finditer(scrub):
            tok = m.group(1).lower()
            kind = "invoke-expression" if tok != "iex" else "iex-alias"
            # Compute the column of the matched token (group 1), not
            # the leading whitespace before it.
            col = m.start(1) + 1
            findings.append((path, idx, col, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_powershell_file(sub):
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
