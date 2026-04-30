#!/usr/bin/env python3
"""llm-output-nodejs-child-process-exec-user-input-detector.

Pure-stdlib single-pass line scanner that flags JavaScript / TypeScript
source where Node.js `child_process.exec` (or `execSync`) is called
with what looks like user-controlled input concatenated or
template-interpolated into the command string. This is the canonical
shell-injection footgun an LLM emits when asked to "run a shell
command with the user's argument".

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

# A "user-input-ish" identifier or property access. Intentionally
# heuristic: matches the lexical surface most LLM-generated handlers
# reach for (req.query.X, req.body.X, req.params.X, process.argv[N],
# process.env.X used as command, plus generic names like `userInput`,
# `input`, `cmd`, `payload`, `query`).
_USER_INPUT_TOKEN = (
    r"(?:"
    r"req\.(?:query|body|params|headers)(?:\.[A-Za-z_$][\w$]*)?"
    r"|process\.argv\s*\[\s*\d+\s*\]"
    r"|process\.env\.[A-Za-z_$][\w$]*"
    r"|(?:user|userInput|input|cmd|command|payload|arg|args|query|"
    r"filename|filepath|path|target|host|url|name)"
    r"(?:\.[A-Za-z_$][\w$]*)?"
    r")"
)

# `exec(` or `execSync(` or `child_process.exec(` followed soon by a
# string that uses string concatenation (`+`) or a template literal
# (backticks with `${...}`) referencing a user-input-ish token.
_EXEC_CALL = (
    r"(?:child_process\s*\.\s*)?exec(?:Sync)?\s*\("
)

_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "exec(...) with template literal interpolating user input",
        re.compile(
            _EXEC_CALL
            + r"[^)]*?`[^`]*\$\{\s*"
            + _USER_INPUT_TOKEN
            + r"\b"
        ),
    ),
    (
        "exec(...) with string concatenation of user input",
        re.compile(
            _EXEC_CALL
            + r"[^)]*?['\"][^'\"]*['\"]\s*\+\s*"
            + _USER_INPUT_TOKEN
            + r"\b"
        ),
    ),
    (
        "exec(...) with user-input identifier as first argument",
        re.compile(
            _EXEC_CALL + r"\s*" + _USER_INPUT_TOKEN + r"\s*[,)]"
        ),
    ),
    (
        "exec(...) with user input prefix-concatenated to literal",
        re.compile(
            _EXEC_CALL
            + r"\s*"
            + _USER_INPUT_TOKEN
            + r"\s*\+\s*['\"]"
        ),
    ),
]

_OK_MARKER = "// child-process-exec-ok"

_LINE_COMMENT = re.compile(r"//.*$")
# A best-effort /* ... */ stripper that handles balanced single-line
# block comments. Multi-line block comments are tracked across lines
# in scan_file().
_BLOCK_COMMENT_SAME_LINE = re.compile(r"/\*.*?\*/")


def _strip_comments(line: str) -> str:
    line = _BLOCK_COMMENT_SAME_LINE.sub(" ", line)
    line = _LINE_COMMENT.sub("", line)
    return line


def _iter_js_files(paths: Iterable[str]) -> Iterable[str]:
    exts = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                if os.path.basename(root).startswith("."):
                    continue
                for f in files:
                    if f.endswith(exts):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    in_block = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if _OK_MARKER in raw:
                    continue
                line = raw
                # multi-line /* ... */ tracking
                if in_block:
                    end = line.find("*/")
                    if end == -1:
                        continue
                    line = line[end + 2 :]
                    in_block = False
                # check for opening block comment with no close
                start = line.find("/*")
                if start != -1 and line.find("*/", start + 2) == -1:
                    in_block = True
                    line = line[:start]
                code = _strip_comments(line)
                for label, pat in _PATTERNS:
                    if pat.search(code):
                        findings.append((lineno, label, raw.rstrip("\n")))
                        break
    except OSError as exc:
        print(f"warn: could not read {path}: {exc}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__ or "", file=sys.stderr)
        return 2
    total = 0
    for fpath in _iter_js_files(argv[1:]):
        for lineno, label, snippet in scan_file(fpath):
            print(f"{fpath}:{lineno}: {label}: {snippet.strip()}")
            total += 1
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
