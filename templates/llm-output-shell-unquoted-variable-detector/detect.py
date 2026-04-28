#!/usr/bin/env python3
"""llm-output-shell-unquoted-variable-detector.

Pure-stdlib, code-fence-aware detector for unquoted shell variable
expansions in fenced shell code blocks emitted by an LLM.

Why it matters
--------------
Unquoted ``$var`` / ``${var}`` / ``$(cmd)`` expansions in POSIX
shell are a well-known foot-gun: when the value contains spaces,
globs, or is empty, the shell performs word-splitting and pathname
expansion, which routinely turns innocuous-looking snippets into
data-loss bugs (e.g. ``rm -rf $dir`` when ``dir`` is empty becomes
``rm -rf``; ``cp $src $dst`` when ``src`` contains a space copies
two wrong files). LLMs frequently emit unquoted expansions in
"copy-paste this" examples because the training corpus is full of
them. This detector flags them at emit time so they can be
re-prompted before a user runs them.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {sh, bash, shell, zsh,
ksh, posix}, and reports each unquoted expansion.

Output: one finding per line on stdout, of the form::

    block=<N> line=<L> col=<C> kind=<k> token=<expansion>

Trailing summary ``total_findings=<N> blocks_checked=<M>`` is
written to stderr. Exit code 0 if no findings, 1 if any, 2 on
bad usage.

What it flags
-------------
    unquoted_var          ``$name`` or ``${name}`` not inside single
                          or double quotes.
    unquoted_cmdsub       ``$(...)`` not inside single or double
                          quotes.

Out of scope (deliberately): backtick command substitution,
arithmetic ``$((...))``, special params like ``$?``
``$$`` ``$#`` ``$@`` ``$*`` ``$!`` ``$0``..``$9``, expansions on
the *left* side of an assignment (``var=$other`` is conventionally
fine), expansions inside ``[[ ... ]]`` (bash-only, no
word-splitting). Heredoc bodies are skipped. Comments are skipped.
This is a *first-line-defense* sniff test, not a shellcheck
replacement.
"""
from __future__ import annotations

import sys
from typing import List, Tuple


_SHELL_TAGS = {"sh", "bash", "shell", "zsh", "ksh", "posix"}

# Special parameters that never need quoting for word-splitting safety
# in the way regular vars do (or are syntactically distinct).
_SPECIAL_PARAMS = set("?$#@*!0123456789-_")


def extract_shell_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each shell block.

    start_line_no is the 1-indexed line of the first line *inside*
    the fence in the original file.
    """
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
                run = 0
                while run < len(stripped) and stripped[run] == ch:
                    run += 1
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2
                    i += 1
                    continue
            i += 1
            continue
        s = stripped.rstrip()
        if s and set(s) == {fence_char} and len(s) >= fence_len:
            if fence_tag in _SHELL_TAGS:
                block_idx += 1
                blocks.append((block_idx, body_start, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    if in_fence and fence_tag in _SHELL_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))
    return blocks


def _strip_heredoc_bodies(src_lines: List[str]) -> List[str]:
    """Replace heredoc body lines with empty strings so we don't scan them.

    Recognises ``<<WORD`` and ``<<-WORD`` (with optional quoting around
    WORD). Preserves line count so line numbers stay aligned.
    """
    out = list(src_lines)
    i = 0
    while i < len(out):
        line = out[i]
        # crude but adequate: look for `<<` or `<<-` followed by a word
        idx = line.find("<<")
        if idx == -1:
            i += 1
            continue
        rest = line[idx + 2:]
        if rest.startswith("-"):
            rest = rest[1:]
        # strip optional surrounding quotes
        rest = rest.lstrip()
        if not rest:
            i += 1
            continue
        q = ""
        if rest[0] in ("'", '"'):
            q = rest[0]
            end = rest.find(q, 1)
            if end == -1:
                i += 1
                continue
            word = rest[1:end]
        else:
            j = 0
            while j < len(rest) and (rest[j].isalnum() or rest[j] == "_"):
                j += 1
            word = rest[:j]
        if not word:
            i += 1
            continue
        # consume body until a line that is exactly `word` (after lstrip
        # for `<<-`)
        i += 1
        while i < len(out):
            candidate = out[i].strip() if "<<-" in line else out[i]
            if candidate.rstrip() == word or out[i].strip() == word:
                break
            out[i] = ""
            i += 1
        i += 1
    return out


def _scan_line(line: str) -> List[Tuple[int, str, str]]:
    """Return [(col, kind, token)] of unquoted expansions on this line.

    col is 1-indexed.
    """
    findings: List[Tuple[int, str, str]] = []
    # strip comment tail (# preceded by start-of-line or whitespace and
    # not inside quotes)
    in_s = False
    in_d = False
    j = 0
    n = len(line)
    while j < n:
        c = line[j]
        if c == "'" and not in_d:
            in_s = not in_s
            j += 1
            continue
        if c == '"' and not in_s:
            in_d = not in_d
            j += 1
            continue
        if c == "\\" and j + 1 < n and not in_s:
            j += 2
            continue
        if c == "#" and not in_s and not in_d:
            if j == 0 or line[j - 1].isspace():
                break  # rest is comment
        if c == "$" and not in_s and not in_d and j + 1 < n:
            nxt = line[j + 1]
            if nxt == "(":
                # $(...) — find matching close paren (depth-tracked,
                # simple, no nested quotes parsing inside)
                depth = 1
                k = j + 2
                while k < n and depth > 0:
                    if line[k] == "(":
                        depth += 1
                    elif line[k] == ")":
                        depth -= 1
                    k += 1
                token = line[j:k]
                findings.append((j + 1, "unquoted_cmdsub", token))
                j = k
                continue
            if nxt == "{":
                end = line.find("}", j + 2)
                if end == -1:
                    j += 1
                    continue
                name = line[j + 2:end]
                bare = name.split(":", 1)[0].split("#", 1)[0].split("%", 1)[0]
                if bare and bare not in _SPECIAL_PARAMS:
                    token = line[j:end + 1]
                    findings.append((j + 1, "unquoted_var", token))
                j = end + 1
                continue
            if nxt.isalpha() or nxt == "_":
                k = j + 1
                while k < n and (line[k].isalnum() or line[k] == "_"):
                    k += 1
                token = line[j:k]
                findings.append((j + 1, "unquoted_var", token))
                j = k
                continue
            # special params: $?, $$, $#, $@, $*, $!, $0..$9, $-, $_
            if nxt in _SPECIAL_PARAMS:
                j += 2
                continue
        j += 1
    return findings


def detect_in_block(body: str) -> List[Tuple[int, int, str, str]]:
    """Return list of (line_no, col, kind, token) findings within block.

    line_no is 1-indexed within the block.
    """
    findings: List[Tuple[int, int, str, str]] = []
    raw_lines = body.split("\n")
    scrubbed = _strip_heredoc_bodies(raw_lines)
    for lineno, line in enumerate(scrubbed, start=1):
        if not line:
            continue
        # skip pure comment lines and blanks
        s = line.lstrip()
        if not s or s.startswith("#"):
            continue
        # skip assignment-only lines: NAME=value with no command after
        # (heuristic: first token matches NAME=...; we still scan the
        # value, but skip if the *only* expansion is the RHS of a
        # standalone assignment)
        for col, kind, token in _scan_line(line):
            if _is_assignment_rhs_only(line, col):
                continue
            findings.append((lineno, col, kind, token))
    return findings


def _is_assignment_rhs_only(line: str, col: int) -> bool:
    """True if `line` is a bare assignment NAME=... and `col` is in the RHS."""
    s = line.lstrip()
    leading = len(line) - len(s)
    # NAME chars
    j = 0
    while j < len(s) and (s[j].isalnum() or s[j] == "_"):
        j += 1
    if j == 0 or j >= len(s) or s[j] != "=":
        return False
    eq_col = leading + j + 1  # 1-indexed col of '='
    if col <= eq_col:
        return False
    # ensure there's no `;` or `&&` or `||` before col turning it into
    # a command context
    rhs = line[eq_col:col - 1]
    for sep in (";", "&&", "||", "|", "&"):
        if sep in rhs:
            return False
    # also: there must be no command before the assignment (e.g.
    # `export NAME=...` or `local NAME=...` — those are still
    # assignments, treat as such)
    pre = line[:leading].strip() or ""
    head = line[leading:leading + j]
    head_ctx = line[:leading + j].split()
    if head_ctx and head_ctx[-1] == head:
        first = head_ctx[0]
        if first in (head, "export", "local", "readonly", "declare", "typeset"):
            return True
    return False


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_shell_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for lineno, col, kind, token in detect_in_block(body):
            total += 1
            print(f"block={block_idx} line={lineno} col={col} "
                  f"kind={kind} token={token}")
    print(f"total_findings={total} blocks_checked={len(blocks)}",
          file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
