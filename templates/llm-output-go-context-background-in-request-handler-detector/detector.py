#!/usr/bin/env python3
"""llm-output-go-context-background-in-request-handler-detector.

Pure-stdlib python3 line scanner that flags Go HTTP handler / gRPC
handler code which uses ``context.Background()`` or
``context.TODO()`` for an outbound call from inside a function that
already has a request-scoped ``context.Context`` available.

When a handler ignores the request context and constructs a fresh
``context.Background()`` for downstream calls (DB query, RPC, HTTP
client), it discards the request's deadline, cancellation signal,
trace IDs, and any auth metadata propagated through the context.
The classic symptom is a request that the client gave up on five
seconds ago, but the server keeps a connection pinned to the DB for
another minute because the inner query was issued with
``context.Background()``.

LLMs reach for ``context.Background()`` because:

1. They saw it in a snippet that initialised a long-lived background
   worker and pattern-matched without realising the new call site is
   request-scoped.
2. They wanted to "decouple" the inner call from a flaky upstream.
3. They could not name the parameter (``ctx`` vs ``r.Context()``) and
   ``context.Background()`` always compiles.

This detector is conservative: it only flags ``context.Background()``
or ``context.TODO()`` calls that appear inside a function which has
either:

* a parameter typed ``context.Context`` (any name), OR
* a parameter named ``r`` / ``req`` / ``request`` typed
  ``*http.Request`` (so ``r.Context()`` is reachable).

Detector only. Reports findings to stdout. Never executes input.

Usage:
    python3 detector.py <file-or-directory> [...]

Exit codes:
    0  no findings
    1  one or more findings
    2  usage error
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_OK_MARKER = "// ctx-background-ok"

EXTS = {".go"}

# Function declaration / method declaration. We capture the parameter
# list so we can check it for a context.Context or *http.Request.
_FUNC_DECL = re.compile(
    r"""^\s*func\s*(?:\([^)]*\)\s*)?[A-Za-z_]\w*\s*\((?P<params>[^)]*)\)""",
    re.MULTILINE,
)

# Anonymous function literal (closure) starting on this line.
_FUNC_LIT = re.compile(r"""\bfunc\s*\((?P<params>[^)]*)\)""")

_HAS_CTX_PARAM = re.compile(r"""\bcontext\.Context\b""")
_HAS_HTTP_REQ_PARAM = re.compile(
    r"""\b(?:r|req|request)\s+\*\s*http\.Request\b"""
)

_BG_CALL = re.compile(r"""\bcontext\.(?:Background|TODO)\s*\(\s*\)""")


def _strip_line_comment(line: str) -> str:
    """Drop // comments outside of strings / runes (best-effort)."""
    out: List[str] = []
    in_str: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch in ("'", '"', "`"):
                in_str = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        if ch == "\\" and i + 1 < n and in_str != "`":
            out.append(line[i + 1])
            i += 2
            continue
        if ch == in_str:
            in_str = None
        i += 1
    return "".join(out)


def _iter_target_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                if os.path.basename(root).startswith("."):
                    continue
                for f in files:
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def _params_have_request_scope(params: str) -> bool:
    if _HAS_CTX_PARAM.search(params):
        return True
    if _HAS_HTTP_REQ_PARAM.search(params):
        return True
    return False


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    """Walk the file tracking brace depth and the request-scope flag of
    the innermost function whose body we are inside.

    The scope stack stores tuples ``(open_brace_depth, has_request_scope)``.
    When brace depth drops back to ``open_brace_depth``, that scope ends.
    """
    findings: List[Tuple[int, str, str]] = []
    stack: List[Tuple[int, bool]] = []
    depth = 0
    in_block_comment = False

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw

                # Strip /* ... */ block comments (line-by-line).
                if in_block_comment:
                    end = line.find("*/")
                    if end == -1:
                        # whole line is comment
                        continue
                    line = line[end + 2 :]
                    in_block_comment = False
                while True:
                    start = line.find("/*")
                    if start == -1:
                        break
                    end = line.find("*/", start + 2)
                    if end == -1:
                        in_block_comment = True
                        line = line[:start]
                        break
                    line = line[:start] + " " * (end + 2 - start) + line[end + 2 :]

                code = _strip_line_comment(line)

                # Detect function declarations / closures opening on this
                # line. We treat both decl and literal as scope-introducing
                # if the same line contains an opening brace.
                pending_scopes: List[bool] = []
                for m in _FUNC_DECL.finditer(code):
                    pending_scopes.append(_params_have_request_scope(m.group("params")))
                for m in _FUNC_LIT.finditer(code):
                    # Skip if this match overlaps with a func decl already
                    # captured (decl regex also matches closures starting
                    # the line). Heuristic: closures appear mid-line.
                    if m.start() == 0:
                        continue
                    pending_scopes.append(_params_have_request_scope(m.group("params")))

                # Walk the line char by char to track braces. When we hit
                # an opening brace and we still have a pending scope, pop
                # it from the queue and push onto the stack.
                pending_iter = iter(pending_scopes)
                next_pending = next(pending_iter, None)

                # Check for a Background() / TODO() call BEFORE we update
                # depth, so the call is attributed to the enclosing scope.
                if _BG_CALL.search(code) and _OK_MARKER not in raw:
                    if stack and stack[-1][1]:
                        findings.append(
                            (
                                lineno,
                                "context.Background/TODO inside request-scoped handler",
                                raw.rstrip("\n"),
                            )
                        )

                for ch in code:
                    if ch == "{":
                        if next_pending is not None:
                            stack.append((depth, next_pending))
                            next_pending = next(pending_iter, None)
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if stack and stack[-1][0] == depth:
                            stack.pop()
    except OSError as exc:
        print(f"warn: could not read {path}: {exc}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__ or "", file=sys.stderr)
        return 2
    total = 0
    for fpath in _iter_target_files(argv[1:]):
        for lineno, label, snippet in scan_file(fpath):
            print(f"{fpath}:{lineno}: {label}: {snippet.strip()}")
            total += 1
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
