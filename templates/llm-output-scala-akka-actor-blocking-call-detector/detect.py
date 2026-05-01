#!/usr/bin/env python3
"""Detect blocking calls inside Akka actor message handlers in LLM-emitted Scala.

LLMs writing Akka classic / typed actors frequently emit blocking calls
inside ``receive`` / ``Behaviors.receive*`` / ``onMessage`` bodies::

    def receive: Receive = {
      case Fetch(id) =>
        val row = Await.result(repo.find(id), 5.seconds)
        sender() ! row
    }

Blocking the actor thread starves the dispatcher, deadlocks the
ActorSystem under load, and defeats Akka's whole back-pressure model.
The Akka docs are explicit: never block in an actor; pipe Future
results back with ``pipeTo(self)`` and handle them as a follow-up
message, or run the blocking work on a dedicated dispatcher.

What this flags
---------------
A line in a ``.scala`` / ``.sc`` file that:

1. Sits inside what looks like an actor message handler body
   (``receive``/``receiveCommand``/``Behaviors.receive``/``onMessage``
   region) AND
2. Calls a known blocking sink:
   ``Await.result``, ``Await.ready``, ``Thread.sleep``,
   ``concurrent.blocking``, ``CountDownLatch.await``,
   ``Future.blocking``, ``BlockingQueue.take``.

The handler region is approximated by tracking brace depth from the
first opening brace of a recognised handler header to the matching
close, plus a small lookahead that also covers single-case lambdas
like ``Behaviors.receiveMessage { msg => ... }``.

What this does NOT flag
-----------------------
* Blocking calls outside any actor handler (e.g. in ``main``, in tests
  marked ``// blocking-ok``, in companion objects).
* Lines suffixed with ``// blocking-ok``.
* Sinks inside ``//`` comments or string literals.
* Files that contain no actor header at all.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// blocking-ok"

# Headers that open an actor message-handling region.
RE_HANDLER_HEADER = re.compile(
    r"\b("
    r"def\s+receive(?:Command|Recover)?\s*(?::\s*\w[\w.]*)?\s*[:=]|"
    r"Behaviors\s*\.\s*receive(?:Message|Signal|Partial)?\b|"
    r"onMessage\s*(?:\[[^\]]*\])?\s*\(|"
    r"Receive\s*\{"
    r")"
)

# Blocking sinks.
RE_SINK = re.compile(
    r"\b("
    r"Await\s*\.\s*result|"
    r"Await\s*\.\s*ready|"
    r"Thread\s*\.\s*sleep|"
    r"concurrent\s*\.\s*blocking|"
    r"scala\s*\.\s*concurrent\s*\.\s*blocking|"
    r"CountDownLatch[^\n]*\.\s*await|"
    r"BlockingQueue[^\n]*\.\s*(?:take|put)|"
    r"\.\s*get\s*\(\s*\)\s*$"  # Future.get() style anti-pattern
    r")"
)


def _strip_strings_and_comments(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_c = False
    while i < n:
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
                out.append('"')
            else:
                out.append(" ")
        elif in_c:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_c = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                # naive: drop rest of line; multi-line block comments
                # are uncommon in LLM-emitted snippets.
                break
            if ch == '"':
                in_s = True
                out.append('"')
            elif ch == "'":
                in_c = True
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    lines = text.splitlines()
    if not any(RE_HANDLER_HEADER.search(_strip_strings_and_comments(ln)) for ln in lines):
        return findings

    in_handler = False
    depth = 0  # brace depth tracked while inside a handler region
    for lineno, raw in enumerate(lines, start=1):
        stripped = _strip_strings_and_comments(raw)

        # Open new handler region on header line.
        if not in_handler and RE_HANDLER_HEADER.search(stripped):
            # find first '{' on this line or following ones; for simplicity
            # we only enter the region when we see '{' on this line.
            if "{" in stripped:
                in_handler = True
                depth = stripped.count("{") - stripped.count("}")
                if depth <= 0:
                    in_handler = False
                    depth = 0
                # check sink on the header line itself (rare)
                if in_handler and SUPPRESS not in raw:
                    m = RE_SINK.search(stripped)
                    if m:
                        sink = re.sub(r"\s+", "", m.group(1))
                        findings.append(
                            (path, lineno, f"akka-actor-blocking-{sink}", raw.rstrip())
                        )
                continue
            # else: header without same-line brace; we'll wait for next '{'
            in_handler = True
            depth = 0
            continue

        if in_handler:
            if depth == 0:
                # haven't seen the opening brace yet — look for it
                if "{" in stripped:
                    depth = stripped.count("{") - stripped.count("}")
                    if depth <= 0:
                        in_handler = False
                        depth = 0
                continue
            depth += stripped.count("{") - stripped.count("}")
            if SUPPRESS not in raw:
                m = RE_SINK.search(stripped)
                if m:
                    sink = re.sub(r"\s+", "", m.group(1))
                    findings.append(
                        (path, lineno, f"akka-actor-blocking-{sink}", raw.rstrip())
                    )
            if depth <= 0:
                in_handler = False
                depth = 0

    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(list(p.rglob("*.scala")) + list(p.rglob("*.sc"))):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
