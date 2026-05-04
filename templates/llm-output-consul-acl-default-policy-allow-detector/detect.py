#!/usr/bin/env python3
"""
llm-output-consul-acl-default-policy-allow-detector

Flags HashiCorp Consul agent configs that set
`acl.default_policy = "allow"` (HCL) or
`"acl": { "default_policy": "allow" }` (JSON), or the equivalent
CLI flag `-default-policy=allow`.

Consul's ACL system uses a default-deny model when
`default_policy = "deny"`: any token without an explicit policy
gets no permissions. Setting `default_policy = "allow"` inverts
that: any unauthenticated request (the "anonymous" token) gets
full read/write access to KV, services, sessions, prepared
queries, and intentions. In an ACL-enabled cluster this is
strictly worse than disabling ACLs, because operators believe
they have access control when they do not.

Maps to:
  - CWE-284: Improper Access Control
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A01:2021 Broken Access Control

Why LLMs ship this
------------------
The Consul "getting started with ACLs" tutorial walks through a
bootstrap procedure where `default_policy = "allow"` is set so the
operator can incrementally migrate. Many blog posts then forget to
flip it to `"deny"` once the migration is done. LLMs trained on
that corpus reproduce the bootstrap snippet as if it were the
recommended steady-state config.

Heuristic
---------
We scan HCL, JSON, YAML (k8s ConfigMap-style), shell command
lines, and systemd unit files for any of the following forms:

  HCL:
    acl {
      default_policy = "allow"
    }
    acl.default_policy = "allow"

  JSON:
    "acl": { "default_policy": "allow" }
    "default_policy": "allow"   (when nested under an "acl" key)

  CLI / systemd:
    consul agent ... -default-policy=allow
    consul agent ... -default-policy allow

Comments (`#`, `//`, `/* */`, `;`) are stripped so commented-out
snippets do not trigger.

We do NOT flag:
  - default_policy = "deny"
  - Discussion / docs / commit messages mentioning the bad value.
  - The legacy top-level `acl_default_policy = "allow"` is *also*
    flagged (older Consul releases used that key).

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_TARGET_NAMES = ("consul.hcl", "consul.json", "agent.hcl", "agent.json")
_TARGET_EXTS = (
    ".hcl", ".json", ".yaml", ".yml", ".conf", ".cfg",
    ".service", ".sh", ".bash", ".envfile", ".snippet",
)


_LINE_COMMENT_HASH = re.compile(r"#.*$")
_LINE_COMMENT_SLASH = re.compile(r"//.*$")
_LINE_COMMENT_SEMI = re.compile(r";.*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(text: str, path_lower: str) -> str:
    text = _BLOCK_COMMENT.sub("", text)
    out = []
    for raw in text.splitlines():
        line = raw
        # JSON has no comments officially; only strip in HCL / shell.
        if path_lower.endswith(".json"):
            out.append(line)
            continue
        # ; only counts as a comment for ini-ish files.
        if path_lower.endswith((".ini", ".cfg", ".conf", ".service")):
            line = _LINE_COMMENT_SEMI.sub("", line)
        line = _LINE_COMMENT_SLASH.sub("", line)
        line = _LINE_COMMENT_HASH.sub("", line)
        out.append(line)
    return "\n".join(out)


# HCL `default_policy = "allow"` (string-quoted).
_HCL_DEFAULT_POLICY = re.compile(
    r"""\bdefault_policy\s*=\s*["']allow["']""",
    re.IGNORECASE,
)
# Legacy top-level key.
_HCL_LEGACY_KEY = re.compile(
    r"""\bacl_default_policy\s*=\s*["']allow["']""",
    re.IGNORECASE,
)
# JSON / YAML "default_policy": "allow"
_JSON_DEFAULT_POLICY = re.compile(
    r'"default_policy"\s*:\s*"allow"',
    re.IGNORECASE,
)
# YAML mapping form: default_policy: allow / "allow"
_YAML_DEFAULT_POLICY = re.compile(
    r"""(?m)^\s*default_policy\s*:\s*["']?allow["']?\s*$""",
    re.IGNORECASE,
)
# CLI flag: -default-policy=allow OR -default-policy allow
_CLI_DEFAULT_POLICY = re.compile(
    r"""(?<![A-Za-z0-9_-])-default-policy(?:\s*=\s*|\s+)["']?allow["']?(?![A-Za-z0-9_-])""",
    re.IGNORECASE,
)


def _under_acl_block(text: str, hit_offset: int) -> bool:
    """Check if hit is inside an `acl { ... }` HCL block or
    `"acl": { ... }` JSON object."""
    prefix = text[:hit_offset]
    # Last `acl` keyword before hit.
    matches = list(re.finditer(r"""(?:["']?acl["']?)\s*[:=]?\s*\{""", prefix, re.IGNORECASE))
    if not matches:
        return False
    last = matches[-1]
    block_start = last.end()  # position right after `{`
    depth = 1
    i = block_start
    while i < hit_offset and depth > 0:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    # If depth still > 0, hit is inside the block.
    return depth > 0


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    path_lower = path.lower()
    cleaned = _strip_comments(text, path_lower)

    # Build line-number lookup.
    def _line_of(off: int) -> int:
        return cleaned.count("\n", 0, off) + 1

    # 1. Legacy top-level key: always a hit.
    for m in _HCL_LEGACY_KEY.finditer(cleaned):
        findings.append(
            f"{path}:{_line_of(m.start())}: consul "
            f"acl_default_policy = \"allow\" -> anonymous tokens "
            f"have full access (CWE-284/CWE-732/CWE-1188)"
        )

    # 2. HCL `default_policy = "allow"` inside `acl { ... }`.
    for m in _HCL_DEFAULT_POLICY.finditer(cleaned):
        if _under_acl_block(cleaned, m.start()):
            findings.append(
                f"{path}:{_line_of(m.start())}: consul acl "
                f"default_policy = \"allow\" -> anonymous tokens "
                f"have full access (CWE-284/CWE-732/CWE-1188)"
            )

    # 3. JSON `"default_policy": "allow"` inside `"acl": { ... }`.
    for m in _JSON_DEFAULT_POLICY.finditer(cleaned):
        if _under_acl_block(cleaned, m.start()):
            findings.append(
                f"{path}:{_line_of(m.start())}: consul acl "
                f"\"default_policy\": \"allow\" -> anonymous "
                f"tokens have full access "
                f"(CWE-284/CWE-732/CWE-1188)"
            )

    # 4. YAML mapping form (k8s ConfigMap embedded YAML).
    for m in _YAML_DEFAULT_POLICY.finditer(cleaned):
        # YAML doesn't have brace blocks; require an `acl:` ancestor
        # by indentation. Cheap heuristic: walk back lines, find the
        # nearest line at strictly lower indent that starts with
        # `acl:` (case-insensitive). If found, flag.
        line_no = _line_of(m.start())
        lines = cleaned.splitlines()
        if line_no - 1 >= len(lines):
            continue
        target_line = lines[line_no - 1]
        target_indent = len(target_line) - len(target_line.lstrip())
        ok = False
        for j in range(line_no - 2, -1, -1):
            cand = lines[j]
            stripped = cand.lstrip()
            if not stripped:
                continue
            cand_indent = len(cand) - len(stripped)
            if cand_indent < target_indent and re.match(
                r"""acl\s*:""", stripped, re.IGNORECASE
            ):
                ok = True
                break
            if cand_indent < target_indent:
                # Different parent; stop walking up.
                break
        if ok:
            findings.append(
                f"{path}:{line_no}: consul acl default_policy: "
                f"allow (YAML) -> anonymous tokens have full "
                f"access (CWE-284/CWE-732/CWE-1188)"
            )

    # 5. CLI flag form anywhere in the file.
    for m in _CLI_DEFAULT_POLICY.finditer(cleaned):
        findings.append(
            f"{path}:{_line_of(m.start())}: consul agent "
            f"-default-policy=allow -> anonymous tokens have "
            f"full access (CWE-284/CWE-732/CWE-1188)"
        )

    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    return scan_text(text, path)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
