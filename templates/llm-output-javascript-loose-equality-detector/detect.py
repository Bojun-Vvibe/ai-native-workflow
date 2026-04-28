#!/usr/bin/env python3
"""llm-output-javascript-loose-equality-detector.

Pure-stdlib, code-fence-aware detector for JavaScript / TypeScript
code blocks that use the loose-equality operators ``==`` and ``!=``
instead of strict ``===`` / ``!==``.

Why it matters
--------------
JavaScript's loose equality applies the abstract-equality algorithm,
which performs implicit type coercion. The classic surprises::

    0      ==  ""        // true
    0      ==  "0"       // true
    false  ==  "0"       // true
    null   ==  undefined // true
    " \t\n" ==  0        // true
    [1]    ==  "1"       // true
    [1,2]  ==  "1,2"     // true

Strict equality (``===`` / ``!==``) does not coerce; it returns
``true`` only when both operands have the same type *and* value.
Eslint's ``eqeqeq`` rule, the Airbnb style guide, the Google style
guide, and the TypeScript recommended config all default to "always
use ``===``" for exactly this reason.

LLMs frequently emit ``if (x == null)`` (which is the only widely
defended use of ``==``, intended to catch both ``null`` and
``undefined``) but they also emit ``if (count == 0)``, ``while (s
!= "")``, ``return code == 200`` — and those are bugs waiting to
happen. This detector flags every loose-equality occurrence, but
exposes a per-finding ``reason`` so a reviewer can quickly skim past
the deliberate ``== null`` idiom if their team allows it.

Detection strategy
------------------
We tokenize each fenced JS/TS block with a small hand-rolled scanner
that understands:

* Single-line ``//`` comments
* Block ``/* ... */`` comments (including nested-style termination)
* Single-quoted, double-quoted, and template-literal strings
  (template-literal backticks), including backslash-style escapes
* Regex literals (rough heuristic: ``/.../flags`` after an operator,
  keyword, or start-of-expression context)

Inside *code* (i.e. not inside a string / comment / regex), we
recognize the operator tokens ``==``, ``!=``, ``===``, ``!==`` and
flag the first two. ``===`` and ``!==`` are accepted.

We also look at the right-hand operand (best-effort, by skipping
whitespace after the operator and reading the next identifier or
literal). If it is the bare token ``null``, we tag the finding with
``reason=loose_eq_null`` so reviewers can decide whether to ignore
that idiom or not. Everything else is ``reason=loose_eq``.

Recognized fenced info-string tags (case-insensitive, first token):
``javascript``, ``js``, ``jsx``, ``typescript``, ``ts``, ``tsx``,
``mjs``, ``cjs``, ``node``.

Usage
-----
    python3 detect.py <markdown_file>

Output: one finding per offending operator on stdout::

    block=<N> start_line=<L> in_block_line=<l> col=<c> op=<op> reason=<r>

Trailing summary ``total_findings=<N> blocks_checked=<M>`` is
printed to stderr. Exit code 0 if no findings, 1 if any.
"""
from __future__ import annotations

import sys
from typing import List, Tuple


_JS_TAGS = {
    "javascript", "js", "jsx",
    "typescript", "ts", "tsx",
    "mjs", "cjs", "node",
}

# Tokens after which a ``/`` is more likely the start of a regex
# literal than a division operator. Conservative; division after
# an identifier or closing paren stays division.
_REGEX_PRECEDERS = {
    "", "(", "[", "{", ",", ";", ":", "!", "?", "&", "|",
    "+", "-", "*", "/", "%", "^", "~",
    "=", "<", ">",
    "return", "typeof", "in", "of", "instanceof",
    "new", "delete", "void", "throw",
    "case", "do", "else", "if", "while", "yield", "await",
}


def extract_js_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for js/ts blocks."""
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
                if fence_tag in _JS_TAGS:
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

    if in_fence and fence_tag in _JS_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))

    return blocks


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ch == "$"


def find_loose_equality(body: str) -> List[Tuple[int, int, str, str]]:
    """Return list of (line_no_1based, col_1based, op, reason)."""
    findings: List[Tuple[int, int, str, str]] = []
    n = len(body)
    i = 0
    line_no = 1
    col = 1
    last_nonspace_token = ""  # for regex-vs-division disambiguation

    def advance(steps: int = 1):
        nonlocal i, line_no, col
        for _ in range(steps):
            if i >= n:
                return
            if body[i] == "\n":
                line_no += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        ch = body[i]

        # Single-line comment
        if ch == "/" and i + 1 < n and body[i + 1] == "/":
            while i < n and body[i] != "\n":
                advance()
            continue

        # Block comment
        if ch == "/" and i + 1 < n and body[i + 1] == "*":
            advance(2)
            while i < n and not (body[i] == "*" and i + 1 < n and body[i + 1] == "/"):
                advance()
            if i < n:
                advance(2)
            continue

        # String literals
        if ch in ("'", '"'):
            quote = ch
            advance()
            while i < n and body[i] != quote:
                if body[i] == "\\" and i + 1 < n:
                    advance(2)
                    continue
                advance()
            if i < n:
                advance()
            last_nonspace_token = "STR"
            continue

        # Template literal
        if ch == "`":
            advance()
            depth = 0
            while i < n:
                if body[i] == "\\" and i + 1 < n:
                    advance(2)
                    continue
                if depth == 0 and body[i] == "`":
                    advance()
                    break
                if body[i] == "$" and i + 1 < n and body[i + 1] == "{":
                    depth += 1
                    advance(2)
                    continue
                if depth > 0 and body[i] == "}":
                    depth -= 1
                    advance()
                    continue
                advance()
            last_nonspace_token = "TPL"
            continue

        # Regex literal — heuristic
        if ch == "/" and last_nonspace_token in _REGEX_PRECEDERS:
            advance()
            in_class = False
            while i < n and body[i] != "\n":
                if body[i] == "\\" and i + 1 < n:
                    advance(2)
                    continue
                if body[i] == "[":
                    in_class = True
                    advance()
                    continue
                if body[i] == "]" and in_class:
                    in_class = False
                    advance()
                    continue
                if body[i] == "/" and not in_class:
                    advance()
                    while i < n and body[i].isalpha():
                        advance()
                    break
                advance()
            last_nonspace_token = "REGEX"
            continue

        # Whitespace
        if ch.isspace():
            advance()
            continue

        # Equality operators — order matters: check 3-char first
        if ch in ("=", "!") and i + 2 < n and body[i + 1] == "=" and body[i + 2] == "=":
            # === or !==
            advance(3)
            last_nonspace_token = "==="
            continue
        if ch in ("=", "!") and i + 1 < n and body[i + 1] == "=":
            # == or !=
            op = body[i:i + 2]
            f_line, f_col = line_no, col
            advance(2)
            # Read RHS operand for null-idiom check
            j = i
            while j < n and body[j] in (" ", "\t"):
                j += 1
            rhs_start = j
            while j < n and _is_ident_char(body[j]):
                j += 1
            rhs = body[rhs_start:j]
            reason = "loose_eq_null" if rhs == "null" else "loose_eq"
            findings.append((f_line, f_col, op, reason))
            last_nonspace_token = op
            continue

        # Identifier or keyword
        if _is_ident_char(ch):
            start = i
            while i < n and _is_ident_char(body[i]):
                advance()
            last_nonspace_token = body[start:i]
            continue

        # Number — skip
        if ch.isdigit() or (ch == "." and i + 1 < n and body[i + 1].isdigit()):
            while i < n and (body[i].isalnum() or body[i] in "._"):
                advance()
            last_nonspace_token = "NUM"
            continue

        # Any other punctuation — single character
        last_nonspace_token = ch
        advance()

    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()

    blocks = extract_js_blocks(src)
    total = 0
    for block_idx, body_start, body in blocks:
        for line_no, col, op, reason in find_loose_equality(body):
            print(
                f"block={block_idx} start_line={body_start} "
                f"in_block_line={line_no} col={col} op={op} reason={reason}"
            )
            total += 1

    print(
        f"total_findings={total} blocks_checked={len(blocks)}",
        file=sys.stderr,
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
