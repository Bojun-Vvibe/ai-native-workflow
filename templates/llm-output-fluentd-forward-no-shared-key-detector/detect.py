#!/usr/bin/env python3
"""
llm-output-fluentd-forward-no-shared-key-detector

Flags Fluentd / Fluent Bit `forward` input (in_forward) configured WITHOUT
a `<security>` block carrying a `shared_key`.

The `forward` input speaks Fluentd's binary forward protocol, typically
on TCP/24224. Without `<security> shared_key </security>` (and ideally
`self_hostname` + per-client `<client>` blocks), ANY process able to
reach the port can:

  * inject arbitrary log events into downstream sinks (S3, Elasticsearch,
    Kafka, Loki) under any `tag` it chooses;
  * forge log records that look like they came from production hosts;
  * trigger `@type exec` / `@type http` output plugins that downstream
    operators trust because "logs only come from our own agents".

This is the Fluentd equivalent of running an open SMTP relay for logs.
The official Fluentd security guide explicitly requires shared_key for
any forward listener exposed beyond loopback.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-287: Improper Authentication.
- CWE-1188: Insecure Default Initialization of Resource.

LLMs ship this misconfig because the in_forward "hello world" snippet
in every blog post is a 3-line `<source> @type forward </source>` with
no security block, and because Fluent Bit's `[INPUT] Name forward` has
no shared-key option in its quickstart.

Stdlib-only. Reads files passed on argv (recurses into dirs).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We parse Fluentd-style `<source>...</source>` blocks and Fluent Bit
`[INPUT] ... Name forward` stanzas. A block is flagged if:

  Fluentd:
    - it contains `@type forward` (or legacy `type forward`), AND
    - it does NOT contain a nested `<security>` block with a
      `shared_key` directive.

  Fluent Bit:
    - an `[INPUT]` section has `Name forward` (case-insensitive), AND
    - the section does NOT contain a `Shared_Key` line, AND
    - it is not bound exclusively to 127.0.0.1 / ::1 / localhost.

We also flag standalone `<source> @type forward </source>` snippets
even outside a wrapping config when the file extension is .conf.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# --- Fluentd <source> block extraction ---------------------------------------

# Match a <source> ... </source> block. Tolerate attributes on the open tag
# (Fluentd allows `<source @label foo>` style? -- not really, but be lenient).
_SOURCE_BLOCK = re.compile(
    r"<source\b[^>]*>(?P<body>.*?)</source>",
    re.DOTALL | re.IGNORECASE,
)

# Inside a body: nested <security> ... </security>.
_SECURITY_BLOCK = re.compile(
    r"<security\b[^>]*>(?P<body>.*?)</security>",
    re.DOTALL | re.IGNORECASE,
)

_TYPE_FORWARD = re.compile(
    r"^\s*(?:@?type)\s+forward\b",
    re.IGNORECASE | re.MULTILINE,
)

_SHARED_KEY = re.compile(
    r"^\s*shared_key\s+\S+",
    re.IGNORECASE | re.MULTILINE,
)

_BIND_LOOPBACK = re.compile(
    r"^\s*bind\s+(?:127\.0\.0\.1|::1|localhost)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# --- Fluent Bit [INPUT] block extraction -------------------------------------

# A Fluent Bit section starts with `[INPUT]` and runs until the next
# `[SECTION]` header or EOF.
_FB_INPUT_BLOCK = re.compile(
    r"^\[INPUT\]\s*\n(?P<body>.*?)(?=^\[[A-Z_]+\]|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)
_FB_NAME_FORWARD = re.compile(
    r"^\s*Name\s+forward\b",
    re.IGNORECASE | re.MULTILINE,
)
_FB_SHARED_KEY = re.compile(
    r"^\s*Shared_Key\s+\S+",
    re.IGNORECASE | re.MULTILINE,
)
_FB_LISTEN_LOOPBACK = re.compile(
    r"^\s*Listen\s+(?:127\.0\.0\.1|::1|localhost)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # Fluentd <source> blocks.
    for m in _SOURCE_BLOCK.finditer(text):
        body = m.group("body")
        if not _TYPE_FORWARD.search(body):
            continue
        # Strip nested <security> bodies and check if any of them
        # carry a shared_key.
        has_shared_key = False
        for sec in _SECURITY_BLOCK.finditer(body):
            if _SHARED_KEY.search(sec.group("body")):
                has_shared_key = True
                break
        if has_shared_key:
            continue
        if _BIND_LOOPBACK.search(body):
            # Loopback-only is acceptable for sidecar-style local pickup.
            continue
        ln = _line_of(text, m.start())
        findings.append(
            f"{path}:{ln}: fluentd <source @type forward> without "
            f"<security> shared_key (CWE-306/CWE-287, anyone on the "
            f"network can inject log records)"
        )

    # Fluent Bit [INPUT] sections.
    for m in _FB_INPUT_BLOCK.finditer(text):
        body = m.group("body")
        if not _FB_NAME_FORWARD.search(body):
            continue
        if _FB_SHARED_KEY.search(body):
            continue
        if _FB_LISTEN_LOOPBACK.search(body):
            continue
        ln = _line_of(text, m.start())
        findings.append(
            f"{path}:{ln}: fluent-bit [INPUT] Name forward without "
            f"Shared_Key (CWE-306, log-injection surface)"
        )

    return findings


_TARGET_EXTS = (".conf", ".cnf", ".yaml", ".yml", ".d")
_TARGET_NAMES = (
    "fluent.conf",
    "td-agent.conf",
    "fluent-bit.conf",
    "fluentbit.conf",
)


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
