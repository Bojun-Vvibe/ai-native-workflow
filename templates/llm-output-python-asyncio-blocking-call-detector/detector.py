#!/usr/bin/env python3
"""
llm-output-python-asyncio-blocking-call-detector

Flags synchronous blocking calls used inside `async def` functions —
e.g. `time.sleep(...)`, `requests.get(...)`, `open(...)` for I/O,
`subprocess.run(...)`, `urllib.request.urlopen(...)`, and `socket.recv`.
These calls block the event loop and are a frequent failure mode in
LLM-generated async code.

Heuristic: walk the AST, find `AsyncFunctionDef` nodes, and within their
bodies look for Call nodes whose callee resolves (textually) to one of
the known blocking APIs. Calls inside nested `def` (sync helper) bodies
are NOT flagged — only calls executed directly on the async path.

Also handles markdown-fenced ```python blocks.

Exit codes:
  0 - no findings
  1 - findings reported
  2 - usage / read error

Usage:
  python3 detector.py <file> [<file> ...]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Map of "callable text" -> short reason. Text forms we recognize:
#   "time.sleep", "requests.get", "subprocess.run", ...
BLOCKING = {
    "time.sleep": "blocks event loop; use `await asyncio.sleep(...)`",
    "requests.get": "sync HTTP; use `aiohttp` / `httpx.AsyncClient`",
    "requests.post": "sync HTTP; use `aiohttp` / `httpx.AsyncClient`",
    "requests.put": "sync HTTP; use `aiohttp` / `httpx.AsyncClient`",
    "requests.delete": "sync HTTP; use `aiohttp` / `httpx.AsyncClient`",
    "requests.request": "sync HTTP; use `aiohttp` / `httpx.AsyncClient`",
    "urllib.request.urlopen": "sync HTTP; use an async HTTP client",
    "subprocess.run": "blocks; use `asyncio.create_subprocess_exec`",
    "subprocess.call": "blocks; use `asyncio.create_subprocess_exec`",
    "subprocess.check_output": "blocks; use `asyncio.create_subprocess_exec`",
    "socket.recv": "blocks; use `asyncio` streams or run_in_executor",
    "socket.send": "blocks; use `asyncio` streams or run_in_executor",
    # `open(...)` is flagged only when called bare (builtin); see below.
    "open": "sync file I/O; use `aiofiles` or `loop.run_in_executor`",
}

FENCE_RE = re.compile(r"^```([a-zA-Z0-9_+\-]*)\s*$")


def _callable_text(func: ast.AST) -> str | None:
    """Render a Call's func as dotted text, e.g. `time.sleep`, or `open`."""
    parts: list[str] = []
    cur: ast.AST | None = func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


class _AsyncBlockingVisitor(ast.NodeVisitor):
    def __init__(self, origin: str, line_offset: int = 0):
        self.origin = origin
        self.line_offset = line_offset
        self.findings: list[str] = []
        # We only flag when we are directly inside an async def, and NOT
        # inside a nested sync def/lambda within it.
        self._async_depth = 0
        self._sync_def_depth = 0

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._async_depth += 1
        self.generic_visit(node)
        self._async_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._sync_def_depth += 1
        self.generic_visit(node)
        self._sync_def_depth -= 1

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._sync_def_depth += 1
        self.generic_visit(node)
        self._sync_def_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if self._async_depth > 0 and self._sync_def_depth == 0:
            text = _callable_text(node.func)
            if text and text in BLOCKING:
                line = (node.lineno or 0) + self.line_offset
                self.findings.append(
                    f"{self.origin}:{line}: blocking call `{text}(...)` "
                    f"inside async function — {BLOCKING[text]}"
                )
        self.generic_visit(node)


def scan_python(source: str, origin: str, line_offset: int = 0) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    v = _AsyncBlockingVisitor(origin, line_offset=line_offset)
    v.visit(tree)
    return v.findings


def scan_markdown(text: str, origin: str) -> list[str]:
    findings: list[str] = []
    in_fence = False
    fence_lang = ""
    fence_start_line = 0
    buf: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence = True
                fence_lang = m.group(1).lower()
                fence_start_line = idx
                buf = []
            else:
                if fence_lang in ("python", "py", "python3"):
                    findings.extend(
                        scan_python(
                            "\n".join(buf),
                            origin,
                            line_offset=fence_start_line,
                        )
                    )
                in_fence = False
                fence_lang = ""
                buf = []
            continue
        if in_fence:
            buf.append(line)
    return findings


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return []
    if path.suffix in (".md", ".markdown"):
        return scan_markdown(text, str(path))
    return scan_python(text, str(path))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file> ...]", file=sys.stderr)
        return 2
    all_findings: list[str] = []
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"error: not found: {p}", file=sys.stderr)
            return 2
        all_findings.extend(scan_file(p))
    for f in all_findings:
        print(f)
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
