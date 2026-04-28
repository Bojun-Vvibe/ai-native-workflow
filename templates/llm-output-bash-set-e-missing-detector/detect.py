#!/usr/bin/env python3
"""llm-output-bash-set-e-missing-detector.

Pure-stdlib, code-fence-aware detector for bash/sh scripts emitted by
an LLM that *look like* they are meant to be run as standalone scripts
(they have a shebang or non-trivial control flow) but are missing a
fail-fast preamble — most commonly `set -e`, `set -eu`, `set -euo
pipefail`, or a `pipefail`-aware equivalent.

Why it matters
--------------
Bash defaults to "best effort": a failing command in the middle of a
script does not abort execution and does not change the exit status of
the script, unless the very last command happens to fail too. So when
an LLM emits an "install everything you need" snippet like::

    #!/usr/bin/env bash
    apt-get update
    apt-get install -y libfoo
    ./configure --prefix=/opt/app
    make
    make install

and `apt-get install` fails because the package name is wrong, every
subsequent step still runs (`./configure` against a half-installed
toolchain, `make` against missing headers, `make install` deploying a
broken binary). The user copy-pastes the snippet, sees a wall of
output, and the script exits 0. They ship the breakage.

`set -e` (abort on any unhandled non-zero exit), combined with
`set -u` (abort on unset variable expansion) and `set -o pipefail`
(propagate the leftmost-non-zero exit through a pipeline), is the
universally-recommended preamble for any non-trivial shell script.

This detector flags fenced bash/sh blocks that meet *both*:

  1. They look like a script — they have a shebang as the first
     non-blank line, OR they contain at least one of the indicators
     {multiple commands separated by newlines AND ANY of: a `for`,
     `while`, `case`, function definition `name() {`, or a pipeline
     `|`} that suggest this is more than a one-liner.
  2. They do *not* contain any of the canonical fail-fast preambles:
     `set -e`, `set -eu`, `set -euo`, `set -eo`, `set -o errexit`,
     or `set -o pipefail` *combined with* `set -e`/`-o errexit`.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {bash, sh, shell, zsh},
and runs the missing-preamble check on each.

Output: one finding per offending block on stdout::

    block=<N> start_line=<L> reason=<r> [shebang=<s>]

Trailing summary `total_findings=<N> blocks_checked=<M>` is printed
to stderr. Exit code 0 if no findings, 1 if any.

Reasons emitted
---------------
    no_set_e_with_shebang        Block starts with a `#!` shebang
                                 but contains no `set -e`-family
                                 directive.
    no_set_e_with_control_flow   Block has no shebang, but contains
                                 a for/while/case/function/pipeline
                                 across multiple lines, and no
                                 `set -e`-family directive.

Out of scope (deliberately)
---------------------------
    * One-liner snippets (single command, single line) — flagging
      these would be pure noise.
    * Scripts that handle errors via explicit `|| exit` / `trap
      ERR` patterns instead of `set -e`. We do not try to detect
      those — false negatives are preferable to false positives
      here.
    * Detection of a *partially-correct* preamble (e.g. `set -e`
      without `-u` or `pipefail`). The opinion encoded here is
      "any `set -e` family is good enough"; teams that want
      stricter checks can layer a separate detector.
"""
from __future__ import annotations

import re
import sys
from typing import List, Tuple


_BASH_TAGS = {"bash", "sh", "shell", "zsh"}

# Lines that count as a fail-fast directive. We accept a fairly
# permissive set so we don't false-positive on teams that prefer
# `set -o errexit` over `set -e`.
_SET_E_PATTERNS = [
    re.compile(r"^\s*set\s+-[A-Za-z]*e[A-Za-z]*\b"),     # -e, -eu, -euo, -eE, etc.
    re.compile(r"^\s*set\s+-o\s+errexit\b"),
]

_PIPEFAIL_PATTERN = re.compile(r"^\s*set\s+-o\s+pipefail\b")

# Heuristic markers that a block is more than a one-liner.
_FOR_PATTERN = re.compile(r"^\s*for\s+\w+\s+in\b")
_WHILE_PATTERN = re.compile(r"^\s*while\s+")
_CASE_PATTERN = re.compile(r"^\s*case\s+.*\s+in\b")
_FUNC_PATTERN = re.compile(r"^\s*\w+\s*\(\)\s*\{")
_FUNC_KEYWORD_PATTERN = re.compile(r"^\s*function\s+\w+")


def extract_bash_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each bash block."""
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = len(stripped) - len(stripped.lstrip(ch))
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2
        else:
            if stripped.startswith(fence_char * fence_len) and \
                    set(stripped) <= {fence_char, " ", "\t"}:
                if fence_tag in _BASH_TAGS:
                    block_idx += 1
                    blocks.append((block_idx, body_start, "\n".join(body)))
                in_fence = False
                fence_char = ""
                fence_len = 0
                fence_tag = ""
                body = []
            else:
                body.append(line)
        i += 1

    if in_fence and fence_tag in _BASH_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))

    return blocks


def _strip_inline_comment(line: str) -> str:
    """Remove a trailing ` # ...` comment, but not a `#` inside quotes.

    Approximate — we do not try to parse shell quoting precisely. We
    only need to keep `#!` shebangs and `set -e` directives intact
    when scanning, both of which never carry inline comments in the
    wild that change their meaning.
    """
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            # `#` only starts a comment when at start-of-line or
            # after whitespace.
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx]
    return line


def has_shebang(body: str) -> Tuple[bool, str]:
    """Return (has_shebang, shebang_line_stripped) for the block."""
    for raw in body.split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#!"):
            return True, s
        return False, ""
    return False, ""


def has_set_e(body: str) -> bool:
    for raw in body.split("\n"):
        cleaned = _strip_inline_comment(raw)
        for pat in _SET_E_PATTERNS:
            if pat.search(cleaned):
                return True
    # Treat `set -o pipefail` followed/preceded by a separate
    # `set -o errexit` as already covered by the loop above. A
    # lone `set -o pipefail` does NOT count — pipefail without
    # errexit still continues past failures.
    return False


def has_control_flow(body: str) -> bool:
    """Return True iff the block looks like more than a one-liner."""
    non_blank = [
        l for l in body.split("\n") if l.strip() and not l.lstrip().startswith("#")
    ]
    if len(non_blank) < 2:
        return False
    pipeline_lines = 0
    for raw in non_blank:
        cleaned = _strip_inline_comment(raw)
        if (
            _FOR_PATTERN.search(cleaned)
            or _WHILE_PATTERN.search(cleaned)
            or _CASE_PATTERN.search(cleaned)
            or _FUNC_PATTERN.search(cleaned)
            or _FUNC_KEYWORD_PATTERN.search(cleaned)
        ):
            return True
        # A `|` outside of `||` and outside of `|&` is a pipeline.
        # Strip those compound tokens first.
        flat = cleaned.replace("||", "  ").replace("|&", "  ")
        if "|" in flat:
            pipeline_lines += 1
    # A single pipeline is suggestive but not strong; require at
    # least 2 lines of script *and* a pipeline somewhere.
    return pipeline_lines >= 1 and len(non_blank) >= 3


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()

    blocks = extract_bash_blocks(src)
    total = 0
    for block_idx, body_start, body in blocks:
        if has_set_e(body):
            continue
        shebang_present, shebang = has_shebang(body)
        if shebang_present:
            print(
                f"block={block_idx} start_line={body_start} "
                f"reason=no_set_e_with_shebang shebang={shebang!r}"
            )
            total += 1
            continue
        if has_control_flow(body):
            print(
                f"block={block_idx} start_line={body_start} "
                f"reason=no_set_e_with_control_flow"
            )
            total += 1

    print(
        f"total_findings={total} blocks_checked={len(blocks)}",
        file=sys.stderr,
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
