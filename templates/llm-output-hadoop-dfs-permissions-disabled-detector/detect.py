#!/usr/bin/env python3
"""
llm-output-hadoop-dfs-permissions-disabled-detector

Flags Hadoop HDFS configurations that disable filesystem
permission checks (dfs.permissions.enabled=false).

Maps to:
- CWE-732: Incorrect Permission Assignment for Critical Resource.
- CWE-285: Improper Authorization.
- CWE-1188: Insecure Default Initialization of Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*-site.xml, *.xml, Dockerfile, docker-compose.*, *.yaml, *.yml, *.sh,
*.bash, *.service, *.env, *.tpl, *.conf, *.properties).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# XML <property><name>dfs.permissions[.enabled]</name><value>false</value></property>
# Tolerant: allow any whitespace / newlines between tags.
_XML_PROP = re.compile(
    r"""<property\b[^>]*>\s*
        (?:<!--.*?-->\s*)?
        (?:<description>.*?</description>\s*)?
        <name>\s*(dfs\.permissions(?:\.enabled)?)\s*</name>\s*
        (?:<description>.*?</description>\s*)?
        <value>\s*(false|0|no)\s*</value>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# CLI: -Ddfs.permissions[.enabled]=false  (also handle quoted forms)
_CLI = re.compile(
    r"""-D\s*dfs\.permissions(?:\.enabled)?\s*=\s*['"]?(false|0|no)['"]?\b""",
    re.IGNORECASE,
)

# key=value form in .properties / .conf / shell env
_KV = re.compile(
    r"""^\s*(?:export\s+)?dfs\.permissions(?:\.enabled)?\s*[:=]\s*['"]?(false|0|no)['"]?\s*$""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*#""")
_XML_COMMENT_BLOCK = re.compile(r"<!--.*?-->", re.DOTALL)

_HADOOP_CTX = re.compile(
    r"""(?i)\b(?:hadoop|hdfs|namenode|datanode)\b|fs\.defaultFS|dfs\.replication|dfs\.blocksize"""
)


def _strip_xml_comments(text: str) -> str:
    return _XML_COMMENT_BLOCK.sub(lambda m: " " * len(m.group(0)), text)


def _strip_inline_shell_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    is_xml = path.lower().endswith(".xml") or "<configuration" in text[:4096]
    in_hadoop_file = bool(_HADOOP_CTX.search(text))

    # XML property scan (XML files only, comments stripped).
    if is_xml:
        scrubbed = _strip_xml_comments(text)
        for m in _XML_PROP.finditer(scrubbed):
            ln = _line_of(scrubbed, m.start())
            findings.append(
                f"{path}:{ln}: hdfs-site.xml sets {m.group(1)}="
                f"{m.group(2)!r}, disabling HDFS permission checks "
                f"(CWE-732/CWE-285): "
                f"{m.group(0).strip()[:200].replace(chr(10), ' ')}"
            )

    # Line-oriented scan for CLI / kv forms.
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_shell_comment(raw)
        if _CLI.search(line):
            findings.append(
                f"{path}:{lineno}: -Ddfs.permissions[.enabled]=false "
                f"on Hadoop CLI disables HDFS permission checks "
                f"(CWE-732/CWE-285): {raw.strip()[:160]}"
            )
            continue
        if in_hadoop_file and _KV.match(line):
            findings.append(
                f"{path}:{lineno}: dfs.permissions[.enabled]=false "
                f"in Hadoop config disables HDFS permission checks "
                f"(CWE-732/CWE-285): {raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "hdfs-site.xml",
    "core-site.xml",
)
_TARGET_EXTS = (
    ".xml", ".yaml", ".yml", ".sh", ".bash", ".service", ".tpl",
    ".env", ".conf", ".properties",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
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
