#!/usr/bin/env python3
"""Detect unsafe PyYAML loader calls.

PyYAML's `yaml.load(stream)` without an explicit safe Loader will
happily honour `!!python/object/apply:os.system` tags and execute
arbitrary code while parsing the document. PyYAML 5.1 started
warning about the missing `Loader=` keyword, but the warning is
trivially silenced and the unsafe behaviour is still available
through `yaml.unsafe_load`, `yaml.Loader`, `yaml.UnsafeLoader`,
and `yaml.FullLoader` (which permits a *subset* of Python tags
including `!!python/name:`).

LLMs almost always emit `yaml.load(open("config.yaml"))` when
asked to "parse a YAML file" because that's the shortest snippet
on Stack Overflow circa 2014. This is the canonical
deserialisation-RCE footgun.

What this flags
---------------
* `yaml.load(...)` with no `Loader=` keyword
* `yaml.load(..., Loader=Loader)`
* `yaml.load(..., Loader=UnsafeLoader)`
* `yaml.load(..., Loader=FullLoader)`
* `yaml.load(..., Loader=yaml.Loader)` and the `yaml.`-prefixed
  variants of the above
* `yaml.unsafe_load(...)` and `yaml.full_load(...)` direct calls
* `yaml.load_all(...)` / `yaml.unsafe_load_all(...)` /
  `yaml.full_load_all(...)` with the same Loader rules

What this does NOT flag
-----------------------
* `yaml.safe_load(...)` and `yaml.safe_load_all(...)`
* `yaml.load(s, Loader=SafeLoader)` /
  `yaml.load(s, Loader=CSafeLoader)` /
  `yaml.load(s, Loader=yaml.SafeLoader)` /
  `yaml.load(s, Loader=yaml.CSafeLoader)`
* `ruamel.yaml.YAML(typ="safe").load(...)` (different API surface)
* Lines marked with a trailing `# yaml-load-ok` comment
* Occurrences inside `#` comments or string literals (so the
  detector does not flag its own docstring)

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python shebang
files).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Always-unsafe call surfaces — fire on sight.
RE_ALWAYS_UNSAFE = re.compile(
    r"\byaml\s*\.\s*(unsafe_load|unsafe_load_all|full_load|full_load_all)\s*\("
)

# Conditionally-unsafe: yaml.load / yaml.load_all — must check Loader=.
RE_LOAD = re.compile(
    r"\byaml\s*\.\s*(load|load_all)\s*\("
)

RE_SUPPRESS = re.compile(r"#\s*yaml-load-ok\b")

# Safe Loader names. We accept bare `SafeLoader`, `CSafeLoader`,
# and `yaml.`-prefixed variants. Anything else (including the
# permissive FullLoader / Loader / UnsafeLoader) is unsafe.
RE_SAFE_LOADER = re.compile(
    r"Loader\s*=\s*(?:yaml\s*\.\s*)?(?:C?SafeLoader)\b"
)

# Detect *any* Loader= kwarg so we can tell "unspecified" from
# "specified-but-unsafe".
RE_LOADER_KW = re.compile(r"Loader\s*=")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Blank Python comment tails and string literal contents,
    preserving column positions and quote tokens. Carries
    triple-quoted string state across lines.
    """
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


def extract_call_args(scrubbed: str, paren_idx: int) -> str | None:
    """Return the text between `(` and the matching `)` on this
    line, or None if the parens are unbalanced.
    """
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


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue
        # Always-unsafe surfaces.
        for m in RE_ALWAYS_UNSAFE.finditer(scrub):
            kind = f"yaml-{m.group(1).replace('_', '-')}"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        # Conditional: yaml.load / yaml.load_all.
        for m in RE_LOAD.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                # Unbalanced — be conservative and flag.
                kind = f"yaml-{m.group(1).replace('_', '-')}-unsafe"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))
                continue
            if RE_SAFE_LOADER.search(args):
                continue
            # Either no Loader= at all, or Loader=<unsafe>.
            if RE_LOADER_KW.search(args):
                kind = f"yaml-{m.group(1).replace('_', '-')}-unsafe-loader"
            else:
                kind = f"yaml-{m.group(1).replace('_', '-')}-no-loader"
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
