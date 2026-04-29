#!/usr/bin/env python3
"""Detect Erlang string-eval / dynamic-compile anti-idioms.

Erlang has no single `eval(String)` builtin the way Python does, but
it ships several stdlib paths that together amount to "compile and
run an arbitrary string at runtime":

    {ok, Tokens, _} = erl_scan:string(Src),
    {ok, Forms}     = erl_parse:parse_exprs(Tokens),
    {value, V, _}   = erl_eval:exprs(Forms, []).

…or the one-shot convenience wrappers in `erl_eval` itself, plus
the runtime-compile path through `compile:forms/1` + `code:load_binary/3`,
plus the `dynamic_compile` contrib that bundles all of the above.

Any of these, fed user-controlled or otherwise untrusted text, is
arbitrary-code execution inside the BEAM VM (full IO, full ports,
full NIF loading).

What this flags
---------------
* `erl_eval:exprs/2`, `erl_eval:expr/2`, `erl_eval:exprs/3`,
  `erl_eval:expr/3`, `erl_eval:exprs/4`, `erl_eval:expr/4`
* `erl_eval:expr_list/...`
* `erl_scan:string/1` and `erl_scan:string/2`        (lexer-from-string)
* `erl_parse:parse_exprs/1`, `erl_parse:parse_form/1`,
  `erl_parse:parse_term/1`                           (parser-from-tokens
                                                      or token-from-string
                                                      pipelines)
* `compile:forms/1`, `compile:forms/2`               (runtime compile)
* `code:load_binary/3`                               (runtime load)
* `dynamic_compile:from_string/1`,
  `dynamic_compile:load_from_string/1`               (contrib helper)
* `M:F(...)` apply pattern where M and F are both bound from
  strings via `list_to_atom/1` / `binary_to_atom/2` on the same
  expression (heuristic, line-local)

Out of scope (deliberately)
---------------------------
* `apply/3` with literal atoms — that's normal dispatch.
* `erlang:apply/3` with a user-supplied module/function but only
  via a *whitelist* — we cannot tell from regex alone, so we flag
  the `list_to_atom` heuristic separately and let the reviewer
  decide.
* Mentions inside `% ...` line comments and string literals
  (`"..."`, `<<"...">>`) are masked out before scanning.

Suppression
-----------
Trailing `% eval-string-ok` comment on the same line suppresses
that finding — use sparingly and never on user-tainted input.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.erl, *.hrl, *.escript.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_ERL_EVAL = re.compile(
    r"\berl_eval\s*:\s*(?:exprs|expr|expr_list)\s*\("
)
RE_ERL_SCAN_STRING = re.compile(
    r"\berl_scan\s*:\s*string\s*\("
)
RE_ERL_PARSE = re.compile(
    r"\berl_parse\s*:\s*(?:parse_exprs|parse_form|parse_term)\s*\("
)
RE_COMPILE_FORMS = re.compile(
    r"\bcompile\s*:\s*forms\s*\("
)
RE_CODE_LOAD_BINARY = re.compile(
    r"\bcode\s*:\s*load_binary\s*\("
)
RE_DYNAMIC_COMPILE = re.compile(
    r"\bdynamic_compile\s*:\s*(?:from_string|load_from_string)\s*\("
)
# Heuristic: same-line `list_to_atom(` AND a `:` apply pattern.
# Two findings: the bare `list_to_atom` / `binary_to_atom` in an
# apply position, and the explicit `apply(list_to_atom(`.
RE_LIST_TO_ATOM_APPLY = re.compile(
    r"\b(?:apply\s*\(\s*)?(?:list_to_atom|binary_to_atom)\s*\("
)

RE_SUPPRESS = re.compile(r"%\s*eval-string-ok\b")


def strip_comments_and_strings(text: str) -> str:
    """Mask `% ...` line comments and Erlang string literals
    (`"..."` and binary `<<"...">>`).

    Erlang string escapes use `\\`. Single-quoted atoms `'...'` are
    *not* string literals in the eval sense — they are atoms and
    we leave them visible (so `'erl_eval':exprs(...)` still flags).
    """
    masked: list[str] = []
    for line in text.splitlines():
        out: list[str] = []
        i = 0
        n = len(line)
        in_dq = False
        while i < n:
            ch = line[i]
            if in_dq:
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == '"':
                    in_dq = False
                    out.append('"')
                    i += 1
                    continue
                out.append(" ")
                i += 1
                continue
            if ch == "%":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
                out.append('"')
                i += 1
                continue
            out.append(ch)
            i += 1
        masked.append("".join(out))
    return "\n".join(masked)


KINDS = (
    ("erl-eval", RE_ERL_EVAL),
    ("erl-scan-string", RE_ERL_SCAN_STRING),
    ("erl-parse", RE_ERL_PARSE),
    ("compile-forms", RE_COMPILE_FORMS),
    ("code-load-binary", RE_CODE_LOAD_BINARY),
    ("dynamic-compile", RE_DYNAMIC_COMPILE),
    ("list-to-atom-apply", RE_LIST_TO_ATOM_APPLY),
)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    raw_lines = text.splitlines()
    suppressed = {i + 1 for i, l in enumerate(raw_lines) if RE_SUPPRESS.search(l)}
    scrubbed_lines = strip_comments_and_strings(text).splitlines()

    findings: list[tuple[int, int, str, str]] = []
    for ln, sl in enumerate(scrubbed_lines, 1):
        if ln in suppressed:
            continue
        for kind, regex in KINDS:
            for m in regex.finditer(sl):
                # `list-to-atom-apply` only flags when there is
                # *also* a `:` apply somewhere on the same line —
                # otherwise it is just a normal atom conversion.
                if kind == "list-to-atom-apply":
                    if ":" not in sl:
                        continue
                snippet = raw_lines[ln - 1].strip() if 1 <= ln <= len(raw_lines) else ""
                findings.append((ln, m.start() + 1, kind, snippet))
    findings.sort()
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    out: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line, col, kind, snippet in scan_text(text):
        out.append((path, line, col, kind, snippet))
    return out


def iter_targets(roots: list[str]):
    suffixes = {".erl", ".hrl", ".escript"}
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in suffixes:
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
