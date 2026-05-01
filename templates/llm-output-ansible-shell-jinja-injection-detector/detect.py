#!/usr/bin/env python3
"""
llm-output-ansible-shell-jinja-injection-detector

Flags Ansible task definitions that pass a Jinja2-templated value
into the ``shell:`` or ``command:`` modules without ``quote``-ing it.

Pattern matched (per task line, line-oriented for zero deps):

    shell: foo {{ user_input }} bar
    command: do-thing --flag {{ x }}
    ansible.builtin.shell: ...{{ ... }}...
    ansible.builtin.command: ...{{ ... }}...

A finding is emitted only when the templated expression is **not**
piped through the ``quote`` filter, i.e. ``{{ x | quote }}`` /
``{{ x|quote }}``. Quoted expansions are how Ansible's docs say to
pass user-controlled values to the shell module.

Maps to CWE-78 (OS Command Injection). The Ansible documentation for
the ``shell`` module explicitly warns:

    If you want to execute a command securely and predictably, it
    may be better to use the ``ansible.builtin.command`` module
    instead. ... If you must use ``shell``, take care to quote
    variables using the ``quote`` filter.

LLMs routinely emit ``shell: rm -rf {{ path }}`` style tasks because
the playbook reads naturally and "works" on the happy-path test
input. The detector catches that whole class.

Stdlib only. Reads files from argv (or recurses into directories for
``*.yaml`` / ``*.yml``). Exit 0 = no findings, 1 = finding(s),
2 = usage error.

Per-line suppression marker:

    shell: do-thing {{ x }}  # llm-allow:ansible-shell-jinja
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

SUPPRESS = "llm-allow:ansible-shell-jinja"

# Match a task line whose key is shell/command (optionally namespaced
# with ansible.builtin., ansible.legacy., or just builtin.) and whose
# value contains a Jinja {{ ... }} expression. Free-form value form:
#
#   - shell: do-thing {{ x }}
#   - name: foo
#     ansible.builtin.command: cmd {{ x }}
#
# We do not handle the multi-line block form (``shell: |``) because
# that is uncommon and the false-positive risk on multi-line bodies
# would be high.
_KEY = (
    r"(?:ansible\.builtin\.|ansible\.legacy\.|builtin\.)?"
    r"(?:shell|command)"
)
_TASK_LINE_RE = re.compile(
    r"^(?P<indent>\s*-?\s*)(?P<key>" + _KEY + r")\s*:\s*(?P<val>.+?)\s*$"
)
_JINJA_RE = re.compile(r"\{\{\s*(?P<expr>.+?)\s*\}\}")


def _expr_is_quoted(expr: str) -> bool:
    """Return True if the Jinja expression terminates in a ``quote``
    filter, e.g. ``x | quote`` or ``x|quote`` or ``x | default('') | quote``.
    """
    # Split on '|' at the top level. Jinja filters chain with '|';
    # the *last* filter is what determines what reaches the shell.
    parts = [p.strip() for p in expr.split("|")]
    if len(parts) < 2:
        return False
    return parts[-1] == "quote" or parts[-1].startswith("quote(")


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        # Drop a trailing '# ...' comment for matching purposes, but
        # keep the original for the suppression check.
        line_for_match = re.sub(r"\s+#.*$", "", raw_line)
        m = _TASK_LINE_RE.match(line_for_match)
        if not m:
            continue
        val = m.group("val")
        # Strip surrounding quotes from a quoted scalar so we can see
        # the inner value as Ansible will render it.
        if (
            len(val) >= 2
            and val[0] == val[-1]
            and val[0] in ("'", '"')
        ):
            val = val[1:-1]
        jinja_hits = list(_JINJA_RE.finditer(val))
        if not jinja_hits:
            continue
        # If every Jinja expression in the line is quoted, skip.
        unsafe = [
            j for j in jinja_hits if not _expr_is_quoted(j.group("expr"))
        ]
        if not unsafe:
            continue
        if SUPPRESS in raw_line:
            continue
        findings.append(
            f"{path}:{i}: ansible-shell-jinja-injection: {raw_line.rstrip()}"
        )
    return findings


def iter_paths(args: Iterable[str]) -> Iterable[str]:
    for a in args:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for fn in sorted(files):
                    if fn.endswith((".yaml", ".yml")):
                        yield os.path.join(root, fn)
        else:
            yield a


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: List[str] = []
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        findings.extend(scan_text(text, path))
    for line in findings:
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
