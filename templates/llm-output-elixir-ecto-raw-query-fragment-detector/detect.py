#!/usr/bin/env python3
"""Detect raw-SQL injection sinks in LLM-emitted Elixir / Ecto code.

LLMs writing Elixir database code frequently emit::

    Repo.query!("SELECT * FROM users WHERE email = '" <> email <> "'")
    Ecto.Adapters.SQL.query!(Repo, "DELETE FROM t WHERE id = " <> id)
    from(u in User, where: fragment("name = '\#{name}'"))

…where user input is concatenated or string-interpolated directly into
SQL. Ecto provides parameterised query placeholders (``$1`` / second
arg of ``Repo.query``) and ``fragment("col = ?", value)`` exactly to
avoid this. The ``Ecto.Query.API.fragment/1`` docs explicitly warn
that interpolating into the SQL string disables parameter binding.

What this flags
---------------
A line in a ``.ex`` / ``.exs`` file that calls a raw-SQL or
``fragment`` sink with a tainted SQL string:

Sinks
~~~~~
* ``Repo.query`` / ``Repo.query!``
* ``Ecto.Adapters.SQL.query`` / ``query!``
* ``Ecto.Adapters.SQL.query_many`` / ``query_many!``
* ``Ecto.Query.API.fragment`` / bare ``fragment(`` inside an Ecto
  query.

Tainted SQL
~~~~~~~~~~~
* The first string argument contains an ``\#{...}`` interpolation, OR
* The first argument is built with ``<>`` string concatenation, OR
* The first argument is a bare variable name (not a literal string).

What this does NOT flag
-----------------------
* ``Repo.query!("SELECT 1")`` — pure literal, no interpolation.
* ``Repo.query!("SELECT * FROM t WHERE id = $1", [id])`` — literal
  with positional parameter list.
* ``fragment("col = ?", value)`` — placeholder form.
* Lines suffixed with ``# sql-ok``.
* Sinks inside ``#`` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# sql-ok"

RE_SINK = re.compile(
    r"\b("
    r"Repo\s*\.\s*query!?|"
    r"Ecto\s*\.\s*Adapters\s*\.\s*SQL\s*\.\s*query(?:_many)?!?|"
    r"fragment"
    r")\s*\("
)


def _strip_comments_outside_strings(line: str) -> tuple[str, str]:
    """Return (code_only, original) where ``code_only`` blanks string
    contents and trims trailing ``#`` comments. Elixir uses ``#`` for
    line comments and ``"`` / ``'`` for strings/charlists. Heredocs
    (``\"\"\"``) are not handled — LLM-emitted Ecto code rarely uses
    them for SQL.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False  # double-quoted string
    in_sq = False  # single-quoted charlist (rare for SQL)
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
            else:
                # preserve interpolation markers so we can detect taint
                if ch == "#" and i + 1 < n and line[i + 1] == "{":
                    out.append("#{")
                    i += 2
                    continue
                if ch == "}":
                    out.append("}")
                else:
                    out.append(" ")
        elif in_sq:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_sq = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "#":
                # line comment
                break
            if ch == '"':
                in_dq = True
                out.append('"')
            elif ch == "'":
                in_sq = True
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out), line


def _extract_arglist(stripped: str, start: int) -> str:
    """Return the inside of the parens that opens at index `start` (a '(')."""
    depth = 0
    out: list[str] = []
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return "".join(out)
        if depth >= 1:
            out.append(ch)
    return "".join(out)


def _first_arg(arglist: str) -> str:
    """Return the first comma-separated argument, respecting brackets/parens
    and double-quoted strings (already blanked by the caller)."""
    depth = 0
    in_dq = False
    out: list[str] = []
    for ch in arglist:
        if in_dq:
            out.append(ch)
            if ch == '"':
                in_dq = False
            continue
        if ch == '"':
            in_dq = True
            out.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return "".join(out)
        out.append(ch)
    return "".join(out)


def _is_tainted_sql_arg(arg: str) -> bool:
    a = arg.strip()
    if not a:
        return False
    # 1. interpolation inside a string literal
    if "#{" in a:
        return True
    # 2. concatenation (<>) anywhere in the argument
    if "<>" in a:
        return True
    # 3. bare identifier (no quote at all): variable reference
    if '"' not in a:
        # Filter out things that are clearly not bare identifiers:
        # function calls without quotes are still suspicious in this
        # context (e.g. build_sql(opts)), so we keep them.
        # Skip if it starts with `[` (positional params list passed
        # positionally is uncommon for the SQL arg).
        if a.startswith("["):
            return False
        # require at least one identifier character
        if re.search(r"[A-Za-z_]", a):
            return True
        return False
    return False


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        stripped, _ = _strip_comments_outside_strings(raw)
        for m in RE_SINK.finditer(stripped):
            paren_idx = stripped.find("(", m.end() - 1)
            if paren_idx < 0:
                continue
            arglist = _extract_arglist(stripped, paren_idx)
            sink_name = re.sub(r"\s+", "", m.group(1))
            # Special-case Repo.query / Ecto.Adapters.SQL.query: the SQL
            # arg may be the second positional after the repo module,
            # i.e. ``Ecto.Adapters.SQL.query(Repo, "SELECT ...", [])``.
            arg = _first_arg(arglist)
            if sink_name.startswith("Ecto.Adapters.SQL.query") and "," in arglist:
                # take second arg
                rest = arglist[len(arg) + 1 :]
                arg = _first_arg(rest)
            if not _is_tainted_sql_arg(arg):
                continue
            kind = f"ecto-raw-sql-{sink_name}"
            findings.append((path, lineno, kind, raw.rstrip()))
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(list(p.rglob("*.ex")) + list(p.rglob("*.exs"))):
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
