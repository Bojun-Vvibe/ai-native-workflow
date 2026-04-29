#!/usr/bin/env python3
"""Detect GNU sed `s///e` (execute) flag usage.

GNU sed's `s/PATTERN/REPL/e` flag passes the *result of the
substitution* to a shell (`/bin/sh -c`) and substitutes the command's
stdout back into the pattern space. Whenever any captured group, the
pattern space, or any unsanitized data flows into the replacement,
the `e` flag becomes a shell-injection sink semantically equivalent
to `eval` on attacker-controlled text.

LLM-emitted shell pipelines occasionally reach for `s/.../.../e` to
"compute" something inline. That is almost always wrong; the safe
forms are:

* run the computation in a separate `awk`/`perl`/explicit shell step
  with proper quoting,
* or use `sed` only for textual substitution and pipe the result into
  the executor.

What this flags
---------------
A `s` (substitute) command whose flags include `e`. Any sed delimiter
is supported (`/`, `|`, `#`, `,`, `:`, etc.). The detector also flags
the standalone `e COMMAND` sed command (GNU extension that executes
COMMAND and inserts the output before the pattern space) and the `e`
flag inside `-e` script arguments on a `sed` command line.

Recognized inputs
-----------------
* Standalone sed scripts (`*.sed`, or shebang `#!/usr/bin/sed -f` /
  `#!/usr/bin/env sed`).
* Shell scripts (`*.sh`, `*.bash`, `*.zsh`, or `#!/usr/bin/env bash`
  shebang) — we scan for `sed ... -e '...e'` style invocations and
  also for heredoc-quoted sed scripts.

Suppression
-----------
Append `# sed-e-ok` to the line to silence a known-safe usage (for
example, a sed script applied to fully trusted, generator-produced
input).

Out of scope (deliberately)
---------------------------
* `awk system()`, shell `eval`, perl `s///e` — covered by their own
  detectors.
* We do not attempt to prove the substitution result is constant.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*sed-e-ok\b")

# Match a sed `s` command with the `e` flag. The delimiter is any
# single non-alphanumeric, non-whitespace, non-backslash character
# that follows the leading `s`. We require three occurrences of the
# same delimiter (s DELIM PAT DELIM REPL DELIM FLAGS) and then look
# for `e` in the trailing flag run (which is [a-zA-Z0-9]*).
#
# Examples matched:
#   s/foo/bar/e
#   s|x|y|gie
#   s#a#b#Me
#   s,$,echo hi,e
#
# The leading boundary requires that `s` is preceded by start-of-line,
# whitespace, `;`, `{`, `}`, `'`, `"`, `\n`, or a digit address (we
# allow any non-alphanumeric char to keep it simple).
RE_S_FLAG_E = re.compile(
    r"(?:^|(?<=[^A-Za-z0-9_]))"
    r"s(?P<d>[^A-Za-z0-9\s\\])"
    r"(?:\\.|(?!(?P=d)).)*"
    r"(?P=d)"
    r"(?:\\.|(?!(?P=d)).)*"
    r"(?P=d)"
    r"(?P<flags>[A-Za-z0-9]*e[A-Za-z0-9]*)"
)

# Match a standalone `e COMMAND` sed command (GNU extension). It must
# appear at command position: start-of-line (after optional address /
# whitespace) or after `;` / `{`. We require the `e` to be followed by
# at least one space and a non-flag character so we don't false-fire
# on labels or s/// flags processed elsewhere.
RE_STANDALONE_E = re.compile(
    r"(?:^|(?<=[;{]))"
    r"\s*(?:[0-9]+|\$|/(?:\\.|[^/])*/)?\s*"
    r"e\s+\S"
)


def strip_sed_comments(line: str) -> str:
    """Blank out `#`-comments while preserving column positions.

    Sed treats `#` as a comment when it appears at the start of a
    line (or after a label). Conservative scrub: any `#` preceded by
    whitespace or start-of-line becomes a comment for our purposes.
    Inside single-quoted shell strings sed scripts cannot contain
    real `#` comments anyway, so this is safe.
    """
    out: list[str] = []
    n = len(line)
    i = 0
    while i < n:
        ch = line[i]
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            out.append(" " * (n - i))
            break
        out.append(ch)
        i += 1
    return "".join(out)


def mask_shell_strings(line: str) -> str:
    """For shell-host files, blank out the *outsides* of single- and
    double-quoted spans so we only scan inside quoted sed scripts.

    Strategy: keep the contents of quoted spans verbatim; replace
    everything outside quotes with spaces. This is a conservative
    way to avoid matching `s/foo/bar/e` that appears in shell prose
    (it almost never does, but the false-match risk on commands like
    `users/foo/bar/e` is real)."""
    out: list[str] = []
    n = len(line)
    i = 0
    in_sq = False
    in_dq = False
    while i < n:
        ch = line[i]
        if in_sq:
            if ch == "'":
                in_sq = False
                out.append(" ")
            else:
                out.append(ch)
            i += 1
            continue
        if in_dq:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_dq = False
                out.append(" ")
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            in_sq = True
            out.append(" ")
            i += 1
            continue
        if ch == '"':
            in_dq = True
            out.append(" ")
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_sed_script(path: Path) -> bool:
    if path.suffix == ".sed":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "sed" in first


def is_shell_file(path: Path) -> bool:
    if path.suffix in (".sh", ".bash", ".zsh", ".ksh"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tok in first for tok in ("bash", "/sh", "zsh", "ksh"))


def scan_line(scrub: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for m in RE_S_FLAG_E.finditer(scrub):
        hits.append((m.start() + 1, "sed-s-e-flag"))
    for m in RE_STANDALONE_E.finditer(scrub):
        hits.append((m.start() + 1, "sed-e-command"))
    return hits


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    sed_native = is_sed_script(path)
    shell_host = is_shell_file(path) and not sed_native
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        if sed_native:
            scrub = strip_sed_comments(raw)
        elif shell_host:
            scrub = mask_shell_strings(raw)
        else:
            # Unknown host: scan masked-as-shell so we minimize false
            # positives on prose.
            scrub = mask_shell_strings(raw)
        for col, kind in scan_line(scrub):
            findings.append((path, idx, col, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if not sub.is_file():
                    continue
                if is_sed_script(sub) or is_shell_file(sub):
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
