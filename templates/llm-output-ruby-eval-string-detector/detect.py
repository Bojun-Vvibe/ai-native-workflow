#!/usr/bin/env python3
"""Detect Ruby string-eval calls: `eval`, `instance_eval`, `class_eval`,
`module_eval`, and the `binding.eval` form.

Why this matters
----------------
Ruby's `Kernel#eval` and the `*_eval` family on Module/Object accept
either a String or a Block. The Block form is fine — it is just a
closure. The String form re-parses the argument as Ruby source code at
runtime, with the same blast radius as `system($USER_INPUT)` when any
piece of the argument is attacker-controlled.

LLM-emitted Ruby reaches for `eval "Foo.new.#{name}"` or
`klass.class_eval(snippet)` to "build a method dynamically." That is
almost always wrong; the safe, idiomatic alternatives are:

* `define_method(:name) { ... }`  instead of `class_eval("def #{name}...")`
* `public_send(name, *args)`      instead of `eval("foo.#{name}")`
* `instance_variable_get(ivar)`   instead of `eval("@#{name}")`

What this flags
---------------
A call to `eval`, `instance_eval`, `class_eval`, or `module_eval`
where the FIRST argument starts with one of:

  "   '   %q   %Q   %w   %W   `   String.new   .to_s   <<~   <<-

…OR is a bareword identifier (a local variable / method call result —
the detector has no way to prove it is constant). The block form
(`obj.instance_eval do ... end` or `obj.instance_eval { ... }`) is
NOT flagged: the next non-space token after the call is `do` or `{`
with no preceding argument.

Also flags: `binding.eval(...)`, `TOPLEVEL_BINDING.eval(...)`,
`Kernel.eval(...)`, and `Kernel#eval(...)`.

Out of scope (deliberately)
---------------------------
* `Object#send` / `public_send` — different (still risky) construct.
* `Module#define_method` with a string body — Ruby ≥ 1.9 only accepts
  a block here, so not a string-eval sink.
* `ERB.new(src).result(binding)` — that's templating; flag separately.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.rb, *.rake, *.gemspec,
Rakefile, Gemfile, and files whose first line is a ruby shebang.

Suppress an audited line with a trailing `# eval-ok` comment.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match: optional receiver (`foo.`, `Kernel.`, `binding.`, etc.) then
# the eval-family method name as a whole word, then `(` or whitespace.
# We capture the call name and the position right after it.
RE_EVAL_CALL = re.compile(
    r"(?:(?<![\w?!])|^)"
    r"(?P<name>(?:Kernel\s*[.#]\s*|binding\s*\.\s*|TOPLEVEL_BINDING\s*\.\s*|"
    r"[A-Za-z_]\w*\s*\.\s*)?"
    r"(?:eval|instance_eval|class_eval|module_eval))"
    r"(?P<sep>\s*\(|\s+)"
)

RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Tokens that, as the first argument, indicate a STRING (not a block).
STRING_STARTERS = (
    '"', "'", "`",
)
STRING_PREFIXES = (
    "%q", "%Q", "%w", "%W", "%i", "%I",
    "<<~", "<<-", "<<\"", "<<'", "<<EOF", "<<HEREDOC",
)


def strip_comments_and_strings(line: str) -> str:
    """Blank out `# ...` comments and the contents of "...", '...',
    `...` strings while preserving column positions. Heredoc bodies
    are NOT tracked across lines (best-effort single-line scrubber).

    We deliberately leave `eval` itself visible by only blanking the
    INSIDE of strings, not their delimiters.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = None  # one of '"', "'", "`"
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                # Could be a comment, but `#{...}` interpolation only
                # happens inside double-quoted/backtick strings, so at
                # the top level any `#` starts a comment.
                out.append(" " * (n - i))
                break
            if ch in ('"', "'", "`"):
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == in_str:
            in_str = None
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def first_arg_is_string_or_dynamic(rest: str) -> bool:
    """Given the text immediately after `eval(` or `eval `, decide if
    the first argument is a String/dynamic expression rather than a
    block. Returns True if it looks like a string-form eval (i.e. we
    should flag).
    """
    s = rest.lstrip()
    if not s:
        return False
    # Block form: `eval do ... end` or `eval { ... }` (no arg).
    if s.startswith("do") and (len(s) == 2 or not (s[2].isalnum() or s[2] == "_")):
        return False
    if s.startswith("{"):
        return False
    if s.startswith(")"):
        return False  # eval() with no args — weird but not a sink
    # Definite string literal starts.
    if s[0] in STRING_STARTERS:
        return True
    for p in STRING_PREFIXES:
        if s.startswith(p):
            return True
    # `String.new(...)`, `something.to_s`, method call returning string.
    # We can't prove staticness — flag conservatively if first token is
    # an identifier (variable / method call) or a method-chain.
    if s[0].isalpha() or s[0] == "_" or s[0] == "@" or s[0] == "$":
        return True
    # Parenthesised expression: `eval(("a" + b))` etc.
    if s[0] == "(":
        return True
    return False


def is_ruby_file(path: Path) -> bool:
    if path.suffix in (".rb", ".rake", ".gemspec", ".ru"):
        return True
    if path.name in ("Rakefile", "Gemfile", "Guardfile", "Capfile"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "ruby" in first


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
        for m in RE_EVAL_CALL.finditer(scrub):
            sep = m.group("sep")
            after = scrub[m.end():]
            if sep.strip().endswith("("):
                # `eval(...)` — look at what's inside the parens.
                if not first_arg_is_string_or_dynamic(after):
                    continue
            else:
                # `eval ARG` — bareword call.
                if not first_arg_is_string_or_dynamic(after):
                    continue
            findings.append(
                (path, idx, m.start("name") + 1, "ruby-eval-string", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_ruby_file(sub):
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
