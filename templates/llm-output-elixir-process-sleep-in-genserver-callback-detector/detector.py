#!/usr/bin/env python3
"""
llm-output-elixir-process-sleep-in-genserver-callback-detector

Flags `Process.sleep/1`, `:timer.sleep/1`, and bare `sleep/1` calls
inside GenServer callback bodies (`handle_call`, `handle_cast`,
`handle_info`, `handle_continue`, `init`, `terminate`,
`code_change`, `format_status`) in Elixir sources.

A GenServer is a single-process serializer for its mailbox. Sleeping
inside one of its callbacks parks the *only* process that can drain
that mailbox, so every other client of the GenServer (callers waiting
on `GenServer.call`, casts queued behind the sleep, monitors, and the
supervisor's shutdown signal) blocks for the full sleep duration.
A few hundred milliseconds of `Process.sleep/1` per request is enough
to convert a healthy GenServer into a queue-bomb under modest load.

The correct primitives are `Process.send_after/3`, `:timer.send_after/3`,
or `handle_continue` with state — all of which yield the process so the
mailbox keeps draining.

LLMs reach for `Process.sleep` because it is the most-cited "wait N
milliseconds" snippet in Elixir docs and tutorials, and because the
"don't block a GenServer" rule is process-architecture context rather
than syntactic. Asked to "rate-limit this handler" or "add a small
delay before responding", the model inlines the sleep without noticing
it has just frozen the whole server.

Strategy: single-pass per-line scanner. Mask comments (`#` to EOL) and
string literals (`"..."`, `'...'`, `\"\"\"...\"\"\"`, `'''...'''`,
and Elixir sigils `~s|...|`, `~S|...|`, `~r|...|` etc., for the common
delimiters). Then track `defmodule` nesting and look for the GenServer
callback function heads. When we see `def handle_call(`, etc., we open
a "callback" scope bound to the next matching `do ... end`. Any
`Process.sleep`, `:timer.sleep`, or unqualified `sleep(` inside that
scope is flagged.

Stdlib only.
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


# ---- masking --------------------------------------------------------------

SIGIL_DELIMS = {
    "(": ")",
    "[": "]",
    "{": "}",
    "<": ">",
    "|": "|",
    "/": "/",
    '"': '"',
    "'": "'",
}


def mask_source(text: str) -> str:
    """Replace comments and string literals with spaces, preserving
    line breaks so line numbers remain accurate."""
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        nxt2 = text[i + 2] if i + 2 < n else ""

        # Heredoc strings: """ ... """ or ''' ... '''
        if c in ('"', "'") and nxt == c and nxt2 == c:
            quote3 = c * 3
            out.append(quote3)
            j = text.find(quote3, i + 3)
            if j == -1:
                # Unterminated: blank to end, keeping newlines.
                for k in range(i + 3, n):
                    out.append("\n" if text[k] == "\n" else " ")
                i = n
                continue
            for k in range(i + 3, j):
                out.append("\n" if text[k] == "\n" else " ")
            out.append(quote3)
            i = j + 3
            continue

        # Sigils: ~s| ... |, ~S<...>, ~r/.../ etc. Two-char prefix +
        # optional uppercase letter run is overkill; Elixir sigils are
        # `~` + single letter (case-insensitive) + delimiter.
        if c == "~" and i + 2 < n and text[i + 1].isalpha() and text[i + 2] in SIGIL_DELIMS:
            open_d = text[i + 2]
            close_d = SIGIL_DELIMS[open_d]
            out.append(text[i : i + 3])
            j = i + 3
            depth = 1 if open_d != close_d else 0
            while j < n:
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    out.append("  " if text[j + 1] != "\n" else " \n")
                    j += 2
                    continue
                if open_d != close_d and ch == open_d:
                    depth += 1
                elif ch == close_d:
                    if open_d == close_d or depth == 1:
                        out.append(close_d)
                        j += 1
                        break
                    depth -= 1
                out.append("\n" if ch == "\n" else " ")
                j += 1
            i = j
            continue

        # Single string: " ... " or ' ... '
        if c == '"' or c == "'":
            quote = c
            out.append(quote)
            i += 1
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  " if text[i + 1] != "\n" else " \n")
                    i += 2
                    continue
                if ch == quote:
                    out.append(quote)
                    i += 1
                    break
                if ch == "\n":
                    out.append("\n")
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue

        # Line comment '# ...'
        if c == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for _ in range(i, j):
                out.append(" ")
            i = j
            continue

        out.append(c)
        i += 1
    return "".join(out)


# ---- scope tracking -------------------------------------------------------

CALLBACK_NAMES = (
    "handle_call",
    "handle_cast",
    "handle_info",
    "handle_continue",
    "init",
    "terminate",
    "code_change",
    "format_status",
)

CALLBACK_HEAD_RE = re.compile(
    r"\bdef(?:p)?\s+(" + "|".join(CALLBACK_NAMES) + r")\s*\("
)

# `do` and `end` keywords (whole-word). We treat `, do:` (one-line `do:`)
# specially: a one-liner like `def handle_info(_msg, s), do: {:noreply, s}`
# does not open a multi-line scope.
DO_KEYWORD_RE = re.compile(r"(?<![\w:])do\b")
END_KEYWORD_RE = re.compile(r"\bend\b")
DO_COLON_RE = re.compile(r",\s*do:\s*")

SLEEP_PATTERNS = [
    (re.compile(r"\bProcess\.sleep\s*\("), "Process.sleep"),
    (re.compile(r":timer\.sleep\s*\("), ":timer.sleep"),
    (re.compile(r"(?<![\w\.:]):?\bsleep\s*\("), "sleep"),
]


def _strip_one_liner_do(line: str) -> str:
    """Remove `, do: <expr>` tail so its `do` does not open a scope."""
    return DO_COLON_RE.sub(" ", line)


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    masked = mask_source(text)
    hits: List[Tuple[int, str]] = []

    # Scope stack: list of dicts {"kind": "callback"|"other"}.
    # We open a scope on `do` (or a `def ... do` head) and close on
    # the matching `end` keyword. Elixir's `do/end` blocks are already
    # well-balanced in valid source.
    scope_stack: List[str] = []  # values: "callback" or "other"
    pending_callback = False  # next `do` opens a callback scope

    for ln_idx, raw_line in enumerate(masked.splitlines(), 1):
        # Strip `, do:` one-liner so it doesn't push a scope.
        line = _strip_one_liner_do(raw_line)

        # Detect callback head on this line; if found, the *next* `do`
        # token (probably on the same line) opens a callback scope.
        head_match = CALLBACK_HEAD_RE.search(line)
        if head_match:
            # If the original raw line had `, do:` we treat as one-liner
            # — pending_callback stays false and any sleep on this line
            # is still flagged below by the inline check.
            if DO_COLON_RE.search(raw_line):
                # One-liner callback: examine this very line for sleeps.
                for pat, label in SLEEP_PATTERNS:
                    for m in pat.finditer(raw_line):
                        col = m.start() + 1
                        hits.append(
                            (
                                ln_idx,
                                f"{label} inside one-line GenServer callback "
                                f"{head_match.group(1)} at col {col}: blocks "
                                f"the GenServer mailbox; use Process.send_after "
                                f"or handle_continue",
                            )
                        )
            else:
                pending_callback = True

        # Walk tokens left-to-right: do / end / sleep matches, in column order.
        events: List[Tuple[int, str, object]] = []
        for m in DO_KEYWORD_RE.finditer(line):
            events.append((m.start(), "do", None))
        for m in END_KEYWORD_RE.finditer(line):
            events.append((m.start(), "end", None))
        for pat, label in SLEEP_PATTERNS:
            for m in pat.finditer(line):
                events.append((m.start(), "sleep", label))
        events.sort(key=lambda e: e[0])

        for col, kind, payload in events:
            if kind == "do":
                if pending_callback:
                    scope_stack.append("callback")
                    pending_callback = False
                else:
                    scope_stack.append("other")
            elif kind == "end":
                if scope_stack:
                    scope_stack.pop()
            elif kind == "sleep":
                in_callback = "callback" in scope_stack
                if in_callback:
                    label = payload  # type: ignore[assignment]
                    hits.append(
                        (
                            ln_idx,
                            f"{label} inside GenServer callback at col {col + 1}: "
                            f"blocks the GenServer mailbox; use Process.send_after "
                            f"or handle_continue",
                        )
                    )
    return hits


def iter_ex_files(root: str):
    if os.path.isfile(root):
        if root.endswith((".ex", ".exs")):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in (".git", "_build", "deps", "node_modules")
        ]
        for fn in filenames:
            if fn.endswith((".ex", ".exs")):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_ex_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
