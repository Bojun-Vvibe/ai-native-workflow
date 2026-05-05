#!/usr/bin/env python3
"""Detect Teleport ``auth_service`` YAML configs that disable second-
factor authentication.

Background
----------
Teleport's auth service controls whether users — including the local
``editor`` / ``access`` roles and any SSO-mapped accounts — must
present a second factor (TOTP, WebAuthn / U2F, PIV-style hardware
key) when logging in. The relevant YAML keys live under
``auth_service.authentication``:

.. code-block:: yaml

    auth_service:
      enabled: true
      authentication:
        type: local
        second_factor: off          # <-- danger
        # or:
        second_factor: optional     # <-- still danger: clients can
                                    #     register zero factors and
                                    #     log in with password only

Accepted-as-safe values are ``on``, ``otp``, ``webauthn``, and
``hardware_key`` / ``hardware_key_touch``. ``off`` and ``optional``
both let a user log in with username + password only — for a system
that brokers SSH, kubectl, database, and desktop access into your
fleet, that's a single-factor blast door.

LLMs reach for ``off`` whenever a user pastes "I'm getting locked out
of teleport, fix my config" because the docs' troubleshooting page
mentions it as a temporary recovery option. It then ends up committed
to ``teleport.yaml`` and rolled out fleet-wide.

What's checked (per file)
-------------------------
The file must look like a Teleport config: it must contain the
``auth_service:`` top-level key (or a ``teleport:`` + ``auth_service``
pair). Then the detector flags either of:

* ``authentication.second_factor`` set to ``off`` / ``"off"`` /
  ``false`` / ``no``.
* ``authentication.second_factor`` set to ``optional`` (passwordless
  + factor-less login is permitted).

Comment lines (``#``) and trailing ``# ...`` comments are stripped.
Suppress per-file with ``# teleport-2fa-off-allowed``.

Indentation is tracked manually (no PyYAML dependency — stdlib only)
so the directive must live under an ``authentication:`` block which
itself lives under an ``auth_service:`` block.

CWE refs
~~~~~~~~
* CWE-308: Use of Single-factor Authentication.
* CWE-287: Improper Authentication.
* CWE-1390: Weak Authentication.

Usage
-----
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*teleport-2fa-off-allowed", re.IGNORECASE)

# YAML scalar values that disable 2FA on `second_factor`.
OFF_VALUES = {"off", "false", "no", "0", "disable", "disabled"}
OPTIONAL_VALUES = {"optional"}

KEY_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_inline_comment(value: str) -> str:
    # Strip a trailing `# ...` if it's not inside a quoted string.
    in_single = False
    in_double = False
    for i, ch in enumerate(value):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return value[:i].rstrip()
    return value.rstrip()


def _normalize_scalar(raw: str) -> str:
    v = _strip_inline_comment(raw).strip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        v = v[1:-1]
    return v.lower()


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()

    # Quick sanity: only look at files that mention Teleport's
    # auth_service top-level key.
    if not re.search(r"(?m)^\s*auth_service\s*:", source):
        return findings

    # Walk line-by-line tracking the parent stack via indentation.
    # stack: list of (indent, key)
    stack: List[Tuple[int, str]] = []

    for idx, raw in enumerate(lines, start=1):
        # Skip blank / pure-comment lines, but preserve indentation
        # tracking by ignoring them.
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(raw)
        if not m:
            continue
        indent = len(m.group(1).expandtabs(2))
        key = m.group(2)
        value_raw = m.group(3)

        # Pop deeper / equal-indent frames.
        while stack and stack[-1][0] >= indent:
            stack.pop()

        # Are we inside auth_service.authentication ?
        parents = [k for _, k in stack]
        is_under_auth_service_authn = (
            "auth_service" in parents and "authentication" in parents
            and parents.index("auth_service") < parents.index("authentication")
        )

        if key == "second_factor" and is_under_auth_service_authn and value_raw:
            v = _normalize_scalar(value_raw)
            if v in OFF_VALUES:
                findings.append(
                    (
                        idx,
                        "auth_service.authentication.second_factor is "
                        f"\"{v}\" — single-factor login (password only) "
                        "permitted",
                    )
                )
            elif v in OPTIONAL_VALUES:
                findings.append(
                    (
                        idx,
                        "auth_service.authentication.second_factor is "
                        "\"optional\" — clients may register zero factors "
                        "and authenticate with password only",
                    )
                )

        # Push this key as a parent only if its value is empty (i.e.
        # it opens a sub-mapping). YAML `key: value` on one line is a
        # leaf and does not become a parent.
        cleaned = _strip_inline_comment(value_raw).strip()
        if not cleaned:
            stack.append((indent, key))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.yaml", "*.yml"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
