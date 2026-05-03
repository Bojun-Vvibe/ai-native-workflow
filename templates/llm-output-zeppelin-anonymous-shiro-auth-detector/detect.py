#!/usr/bin/env python3
"""
llm-output-zeppelin-anonymous-shiro-auth-detector

Flags Apache Zeppelin deployments that leave the Shiro authentication
filter chain wide open to anonymous users. Zeppelin notebooks routinely
embed credentials, run shell / Spark / JDBC interpreters, and expose
results that include PII. An unauthenticated UI on port 8080 is, in
practice, remote code execution as the Zeppelin service account.

The relevant Shiro INI surface is `[urls]`. The default tutorial line
is:

    /** = anon

which assigns the *anonymous* filter to every URL under the Zeppelin
web app, bypassing the form / LDAP / PAM realms configured above it.
The fix is `/** = authc` (or a chain that ends in `authc`).

Zeppelin's own `conf/shiro.ini.template` ships with `/** = anon`
commented out and `/** = authc` active, but every "get Zeppelin running
in 5 minutes" blog reverses that. LLMs that have ingested those blogs
reproduce the insecure form.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-284: Improper Access Control.
- CWE-1188: Insecure Default Initialization of Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
shiro.ini, *.ini, *.properties, and Zeppelin config templates).

Heuristic
---------
Inside the `[urls]` section of a Shiro INI (or any INI-shaped file
that contains a `[urls]` header), we flag any line that:

1. Maps `/**` (or `/api/**`, `/*`) to a chain whose *final* filter is
   `anon`, e.g. `/** = anon`, `/api/** = anon`.
2. Maps `/**` to an empty chain `=` (Shiro treats this as anon).
3. Outside any section, we also flag the bare textual pattern
   ``/** = anon`` because LLMs sometimes paste the snippet without
   the section header.

We do NOT flag:
- `/login = anon` or `/api/version = anon` (intentionally public
  endpoints); we require the path to be one of the catch-alls above.
- Lines inside `#`-style or `;`-style comments.
- A chain that ends in `authc` even if it lists `anon` mid-chain
  (Shiro evaluates left-to-right; the last filter decides).

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# Paths that are catch-alls; mapping any of these to anon means the
# whole UI is open.
_CATCHALL = re.compile(r"""^/(?:\*\*|\*|api/\*\*|api/\*)\s*$""")

# A Shiro section header like `[urls]` or `[main]`.
_SECTION = re.compile(r"""^\s*\[\s*([A-Za-z_][\w-]*)\s*\]\s*$""")

# A bare-snippet pattern: `/** = anon`, tolerant of whitespace.
_BARE_SNIPPET = re.compile(
    r"""(?m)^\s*/\*\*\s*=\s*anon\s*(?:#.*|;.*)?$"""
)

_COMMENT = re.compile(r"""^\s*[#;]""")


def _strip_inline_comment(s: str) -> str:
    # Shiro / INI inline comments use `#` or `;`. We do not need to
    # worry about quoted strings here because Shiro url chains do not
    # contain `#` or `;` in legitimate use.
    for sep in ("#", ";"):
        i = s.find(sep)
        if i >= 0:
            s = s[:i]
    return s.rstrip()


def _final_filter(chain: str) -> str:
    """
    Given a Shiro filter chain like `authc, roles[admin]` or
    `anon` or `authcBasic`, return the name of the final filter
    (the one Shiro uses to decide allow/deny).
    """
    parts = [p.strip() for p in chain.split(",") if p.strip()]
    if not parts:
        return ""
    last = parts[-1]
    # Strip any `[...]` argument list.
    bracket = last.find("[")
    if bracket >= 0:
        last = last[:bracket]
    return last.strip()


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    section = ""
    seen_in_urls = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT.match(raw):
            continue

        m = _SECTION.match(raw)
        if m:
            section = m.group(1).lower()
            continue

        line = _strip_inline_comment(raw)
        if not line.strip():
            continue

        if section == "urls":
            # Expect `path = chain` (Shiro INI key = value).
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if not _CATCHALL.match(key):
                continue
            seen_in_urls = True
            if val == "":
                findings.append(
                    f"{path}:{lineno}: Shiro [urls] maps {key} to an "
                    f"empty filter chain (treated as anon, CWE-306): "
                    f"{raw.strip()[:160]}"
                )
                continue
            if _final_filter(val) == "anon":
                findings.append(
                    f"{path}:{lineno}: Shiro [urls] maps catch-all "
                    f"{key} to anon -- Zeppelin UI is unauthenticated "
                    f"(CWE-306/CWE-284): {raw.strip()[:160]}"
                )

    # Bare-snippet fallback: triggers only if we did NOT already see
    # this pattern inside [urls] (avoids double-counting).
    if not seen_in_urls:
        for m in _BARE_SNIPPET.finditer(text):
            # Compute lineno from offset.
            lineno = text.count("\n", 0, m.start()) + 1
            findings.append(
                f"{path}:{lineno}: bare Shiro snippet `/** = anon` -- "
                f"Zeppelin UI would be unauthenticated (CWE-306): "
                f"{m.group(0).strip()[:160]}"
            )
    return findings


_TARGET_NAMES = ("shiro.ini", "shiro.ini.template")
_TARGET_EXTS = (".ini", ".properties", ".conf", ".tpl", ".template")


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
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
