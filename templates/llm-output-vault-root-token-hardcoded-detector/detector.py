#!/usr/bin/env python3
"""Detect HashiCorp Vault deployments that hardcode a *root* token in
configuration, environment files, or container/orchestrator manifests.

Vault's root token is meant to exist only briefly during the initial
``vault operator init`` flow. It must be revoked once a permanent auth
backend (userpass, OIDC, AppRole, Kubernetes auth, etc.) is configured.
A persisted root token in a config file, env file, or compose/K8s
manifest is equivalent to handing every reader of that file unrestricted
write access to every secret.

What this detector flags
------------------------

A file is flagged when it contains an assignment of either ``VAULT_TOKEN``
or ``VAULT_DEV_ROOT_TOKEN_ID`` to a non-empty literal value that looks
like a baked-in token rather than a runtime reference.

Specifically, an assignment is *bad* when the value:

* Starts with the canonical Vault token prefixes ``hvs.``, ``hvb.``,
  ``s.`` (legacy service token), or ``b.`` (legacy batch token); OR
* Is the well-known dev placeholder ``root``, ``myroot``, ``vault-root``,
  ``rootroot``, ``devroot``, ``mytoken``, ``changeme``; OR
* Is a >= 16 char alphanumeric/dash literal (no ``$`` interpolation, no
  ``${...}``, no ``%(..)s``, no ``<...>`` placeholder) appearing on the
  right-hand side of one of the recognised assignment forms.

An assignment is *good* (ignored) when:

* The value is empty.
* The value is a shell/compose/K8s reference such as ``${VAULT_TOKEN}``,
  ``$VAULT_TOKEN``, ``${VAULT_TOKEN:-}``, ``%(env:VAULT_TOKEN)s``.
* The value resolves through a secret-store reference like
  ``valueFrom: secretKeyRef`` (for K8s manifests, the env entry has no
  inline ``value:`` field).
* The line carries the suppression marker ``# vault-root-token-allowed``.

The detector is regex-based and intentionally conservative. It targets
``.env``-style files, HCL ``vault`` config blocks, Docker-Compose YAML,
Kubernetes manifests, and shell-export snippets. It does not try to
parse arbitrary HCL or YAML; it greps assignment-shaped lines.

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_MARK = "# vault-root-token-allowed"

# Known dev / placeholder values shipped in tutorials.
PLACEHOLDER_VALUES = {
    "root",
    "myroot",
    "vault-root",
    "rootroot",
    "devroot",
    "mytoken",
    "changeme",
}

# Real-looking token prefixes.
TOKEN_PREFIXES = ("hvs.", "hvb.", "s.", "b.")

# Assignment forms we recognise:
#   VAULT_TOKEN=hvs.xxxx
#   VAULT_TOKEN: hvs.xxxx        (compose / k8s env list)
#   VAULT_TOKEN = "hvs.xxxx"     (HCL-ish)
#   token = "hvs.xxxx"           (HCL inside a vault {} block)
#   - name: VAULT_TOKEN          (k8s env entry; pair with `value:`)
#     value: hvs.xxxx
ASSIGN_RE = re.compile(
    r"""^(?P<indent>\s*)
        (?:export\s+)?
        (?P<key>VAULT_TOKEN|VAULT_DEV_ROOT_TOKEN_ID|token)
        \s*(?P<sep>[:=])\s*
        (?P<value>.*?)
        \s*(?:\#.*)?$
    """,
    re.VERBOSE,
)

# K8s style: detect a `name: VAULT_TOKEN` followed (within a few lines)
# by a sibling `value: <literal>` (no valueFrom).
K8S_NAME_RE = re.compile(r"^\s*-?\s*name:\s*['\"]?(VAULT_TOKEN|VAULT_DEV_ROOT_TOKEN_ID)['\"]?\s*$")
K8S_VALUE_RE = re.compile(r"^\s*value:\s*(?P<value>.+?)\s*(?:#.*)?$")
K8S_VALUEFROM_RE = re.compile(r"^\s*valueFrom\s*:\s*$")

# A reference / interpolation looks like one of these.
REFERENCE_RE = re.compile(
    r"""^(?:
            \$\{[^}]+\}        # ${VAR} or ${VAR:-default}
          | \$[A-Za-z_][A-Za-z0-9_]*  # $VAR
          | %\([^)]+\)s        # %(env:..)s
          | <[^>]+>            # <REPLACE_ME>
          | \{\{[^}]+\}\}      # {{ .Values.x }}
        )$
    """,
    re.VERBOSE,
)

# Strip surrounding quotes for the value test.
QUOTE_RE = re.compile(r"""^(['"])(.*)\1$""")


def _looks_like_token_literal(raw: str) -> Tuple[bool, str]:
    """Return (is_bad, reason) for a stripped value."""
    val = raw.strip()
    if not val:
        return False, ""
    m = QUOTE_RE.match(val)
    if m:
        val = m.group(2).strip()
    if not val:
        return False, ""
    if REFERENCE_RE.match(val):
        return False, ""
    low = val.lower()
    if low in PLACEHOLDER_VALUES:
        return True, f"placeholder root-token literal '{val}' baked into config"
    for pref in TOKEN_PREFIXES:
        if val.startswith(pref) and len(val) >= len(pref) + 4:
            return True, f"hardcoded Vault token literal (prefix '{pref}') baked into config"
    # Generic: long alphanumeric literal with no interpolation. Be careful
    # not to flag short toggles; require length >= 16.
    if len(val) >= 16 and re.match(r"^[A-Za-z0-9._\-]+$", val):
        return True, "hardcoded long token-shaped literal assigned to VAULT_TOKEN/root id"
    return False, ""


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()

    # Pass 1: simple assignment lines (env / HCL / compose-string).
    for i, raw in enumerate(lines, 1):
        if SUPPRESS_MARK in raw:
            continue
        m = ASSIGN_RE.match(raw)
        if not m:
            continue
        key = m.group("key")
        # `token = "..."` is interesting only if it is plausibly inside a
        # vault config block (we can't fully parse HCL, but we restrict
        # to files where the surrounding context mentions a Vault config
        # keyword).
        if key == "token":
            ctx_lo = max(0, i - 6)
            ctx = "\n".join(lines[ctx_lo:i])
            if not re.search(
                r"\b(vault|VAULT|seal\s*\"|storage\s*\"|listener\s*\")",
                ctx,
            ):
                continue
        value = m.group("value")
        is_bad, reason = _looks_like_token_literal(value)
        if is_bad:
            findings.append((i, f"{key}: {reason}"))

    # Pass 2: K8s env list pattern.
    i = 0
    while i < len(lines):
        raw = lines[i]
        if SUPPRESS_MARK in raw:
            i += 1
            continue
        if K8S_NAME_RE.match(raw):
            # Look ahead up to 5 lines for a `value:` or `valueFrom:`.
            j = i + 1
            saw_valuefrom = False
            value_line = None
            value_lineno = None
            while j < len(lines) and j <= i + 5:
                nxt = lines[j]
                if K8S_VALUEFROM_RE.match(nxt):
                    saw_valuefrom = True
                    break
                vm = K8S_VALUE_RE.match(nxt)
                if vm:
                    value_line = vm.group("value")
                    value_lineno = j + 1
                    break
                # Stop if we hit another env entry.
                if re.match(r"^\s*-\s*name:", nxt):
                    break
                j += 1
            if not saw_valuefrom and value_line is not None:
                is_bad, reason = _looks_like_token_literal(value_line)
                if is_bad:
                    findings.append(
                        (value_lineno or (i + 1), f"k8s env VAULT_TOKEN: {reason}")
                    )
        i += 1

    # De-dup by (line, reason)
    seen = set()
    out: List[Tuple[int, str]] = []
    for ln, r in findings:
        if (ln, r) in seen:
            continue
        seen.add((ln, r))
        out.append((ln, r))
    out.sort()
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.env", "*.envfile", "*.hcl", "*.yaml", "*.yml", "*.sh", "*.conf"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
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
