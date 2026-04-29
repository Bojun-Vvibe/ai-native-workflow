#!/usr/bin/env python3
"""Detect Groovy dynamic-evaluation calls on string arguments.

In Groovy, several APIs take a String of source code and execute it at
runtime. The big four:

* `Eval.me(STRING)`         / `Eval.x(...)` / `Eval.xy(...)` / `Eval.xyz(...)`
* `new GroovyShell().evaluate(STRING)`  (and `.parse(STRING).run()`)
* `new GroovyShell().run(STRING, ...)`
* `Class.forName("groovy.lang.GroovyClassLoader") ... parseClass(STRING)`

Any of these used on attacker- or developer-templated text is a code-
injection sink with the same blast radius as `Runtime.exec(USER_INPUT)`.
LLM-emitted Groovy frequently reaches for `Eval.me(scriptString)` to
"just run this little snippet" — that is almost always wrong; the safe
forms are an explicit dispatch table or a sandbox `SecureASTCustomizer`
on a dedicated `GroovyShell`.

What this flags
---------------
A bareword call to one of:

* `Eval.me(`, `Eval.x(`, `Eval.xy(`, `Eval.xyz(`
* `.evaluate(` when the receiver chain ends in `GroovyShell` (heuristic:
  `GroovyShell` appears earlier on the same line) OR the call is on a
  variable named `*shell*` / `*Shell*`
* `.parseClass(`           (GroovyClassLoader)
* `GroovyShell(...).run(`  on a string literal/variable

Suppress an audited line with a trailing `// groovy-eval-ok` comment.

Out of scope (deliberately)
---------------------------
* `@CompileStatic` / `@TypeChecked` reflection — different smell.
* `Binding` setup itself — only the eval/run/parse call site is flagged.
* We do not try to prove the argument is a constant.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.groovy, *.gvy, *.gy, *.gradle,
and files whose first line is a `groovy` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Eval.me / Eval.x / Eval.xy / Eval.xyz
RE_EVAL_ME = re.compile(r"\bEval\s*\.\s*(?:me|x|xy|xyz)\s*\(")

# .evaluate( call where line also mentions GroovyShell, or receiver name
# contains "shell" / "Shell" (heuristic, single-line). We capture the
# `.evaluate(` site itself so column is meaningful.
RE_EVALUATE = re.compile(r"\.evaluate\s*\(")

# .parseClass( on a GroovyClassLoader
RE_PARSE_CLASS = re.compile(r"\.parseClass\s*\(")

# new GroovyShell(...).run(  (single-line)
RE_SHELL_RUN = re.compile(r"\bGroovyShell\b[^;\n]*\.run\s*\(")

# Suppression marker.
RE_SUPPRESS = re.compile(r"//\s*groovy-eval-ok\b")

# Heuristic guards for the generic `.evaluate(` rule.
RE_LINE_HAS_SHELL_CTX = re.compile(r"\bGroovyShell\b")
RE_RECEIVER_LOOKS_LIKE_SHELL = re.compile(
    r"(?:^|[^A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*evaluate\s*\("
)


def strip_comments_and_strings(line: str) -> str:
    """Blank out comments and string-literal contents while keeping
    column positions stable.

    Handles: `//` line comments, `/* ... */` single-line block comments,
    `'...'`, `"..."`, and triple-quoted `'''...'''` / `\"\"\"...\"\"\"`
    when they open and close on the same line.

    Multi-line block comments / triple-quoted strings are out of scope
    for this single-pass scrubber; the worst case is a missed flag, not
    a false positive at column position, because the eval keywords are
    matched as whole tokens and never appear inside the string-content
    blanks we emit.
    """
    out: list[str] = []
    i = 0
    n = len(line)

    def emit_blank(k: int) -> None:
        out.append(" " * k)

    in_sq = False  # single-quoted string
    in_dq = False  # double-quoted string

    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""

        if not in_sq and not in_dq:
            # Triple-quoted strings: collapse whole region if it closes
            # on the same line.
            if line.startswith("'''", i):
                end = line.find("'''", i + 3)
                if end == -1:
                    emit_blank(n - i)
                    break
                emit_blank(end + 3 - i)
                i = end + 3
                continue
            if line.startswith('"""', i):
                end = line.find('"""', i + 3)
                if end == -1:
                    emit_blank(n - i)
                    break
                emit_blank(end + 3 - i)
                i = end + 3
                continue
            # Line comment.
            if ch == "/" and nxt == "/":
                emit_blank(n - i)
                break
            # Block comment (single-line only).
            if ch == "/" and nxt == "*":
                end = line.find("*/", i + 2)
                if end == -1:
                    emit_blank(n - i)
                    break
                emit_blank(end + 2 - i)
                i = end + 2
                continue
            if ch == "'":
                in_sq = True
                out.append(ch)
                i += 1
                continue
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        # Inside a string literal.
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if in_sq and ch == "'":
            in_sq = False
            out.append(ch)
            i += 1
            continue
        if in_dq and ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1

    return "".join(out)


def is_groovy_file(path: Path) -> bool:
    if path.suffix in (".groovy", ".gvy", ".gy", ".gradle"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "groovy" in first


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)

        for m in RE_EVAL_ME.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "groovy-eval-me", raw.strip())
            )
        for m in RE_PARSE_CLASS.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "groovy-parseclass", raw.strip())
            )
        for m in RE_SHELL_RUN.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "groovy-shell-run", raw.strip())
            )
        # `.evaluate(` is generic; only flag when the line contextually
        # implicates a GroovyShell receiver.
        line_has_shell = bool(RE_LINE_HAS_SHELL_CTX.search(scrub))
        for m in RE_EVALUATE.finditer(scrub):
            recv_match = None
            for rm in RE_RECEIVER_LOOKS_LIKE_SHELL.finditer(scrub):
                if rm.end() == m.end():
                    recv_match = rm
                    break
            recv_name = recv_match.group(1) if recv_match else ""
            if line_has_shell or "shell" in recv_name.lower():
                findings.append(
                    (path, idx, m.start() + 1, "groovy-shell-evaluate", raw.strip())
                )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_groovy_file(sub):
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
