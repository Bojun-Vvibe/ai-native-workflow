#!/usr/bin/env python3
"""
llm-output-spark-ui-acls-disabled-detector

Flags Apache Spark deployments that explicitly disable Web UI ACLs.

Spark's Web UI (driver port 4040, history server port 18080) exposes:
- the full SQL plan + parameters of every query (including any
  literals — passwords accidentally inlined in queries leak here),
- environment tab including `spark.*.password` / `spark.hadoop.*`
  values (yes, it shows them in plaintext if not redacted),
- thread dumps with stack frames containing arguments,
- `kill` links that terminate running stages / jobs.

`spark.acls.enable` (and the older alias `spark.ui.acls.enable`)
gate all of the above. When set to `false` *and* the UI is reachable
on a routable interface, anyone who can hit port 4040 / 18080 can
read job parameters and kill running jobs.

We also flag `spark.modify.acls=*` and `spark.admin.acls=*` because
those wildcard-grant the same surface to every authenticated user
(or every user, when auth is also off — see sibling detectors).

Maps to:
- CWE-284: Improper Access Control.
- CWE-306: Missing Authentication for Critical Function.
- CWE-732: Incorrect Permission Assignment for Critical Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks spark-defaults.conf, *.conf, *.properties, *.yaml, *.yml,
*.sh, *.bash, *.tpl, and *.tf).

Heuristic
---------
We flag, outside `#` / `//` comments:

1. `spark.acls.enable` set to a falsy value (`false`, `False`, `0`,
   `no`, `off`).
2. `spark.ui.acls.enable` (legacy alias) set to a falsy value.
3. `spark.modify.acls` whose value is exactly `*` (wildcard).
4. `spark.admin.acls`  whose value is exactly `*` (wildcard).
5. CLI / SparkConf forms:
   - `--conf spark.acls.enable=false`
   - `.set("spark.acls.enable", "false")` (Scala / Java / Python).

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_FALSY = {"false", "0", "no", "off"}

# Conf file form: `spark.acls.enable false` or `spark.acls.enable=false`.
_CONF_ACLS_ENABLE = re.compile(
    r"""(?P<key>\bspark\.(?:ui\.)?acls\.enable)\s*[=:\s]\s*"""
    r"""['"]?(?P<val>[A-Za-z0-9_]+)['"]?"""
)

# `spark.modify.acls = *` / `spark.admin.acls = *`.
_CONF_ACLS_WILDCARD = re.compile(
    r"""(?P<key>\bspark\.(?:modify|admin)\.acls)\s*[=:\s]\s*"""
    r"""['"]?(?P<val>\*)['"]?\s*(?:#.*|//.*)?$""",
    re.MULTILINE,
)

# CLI `--conf spark.acls.enable=false`.
_CLI_ACLS = re.compile(
    r"""--conf\s+['"]?spark\.(?:ui\.)?acls\.enable\s*=\s*"""
    r"""(?P<val>[A-Za-z0-9_]+)['"]?"""
)

# SparkConf programmatic form: .set("spark.acls.enable", "false")
# or .setIfMissing(...) or PySpark builder .config("...", "false").
# Tolerant of single / double quotes and Python / Scala / Java spacing.
_PROG_ACLS = re.compile(
    r"""\.(?:set(?:IfMissing)?|config)\s*\(\s*['"]spark\.(?:ui\.)?acls\.enable['"]"""
    r"""\s*,\s*['"](?P<val>[A-Za-z0-9_]+)['"]\s*\)"""
)

# Programmatic wildcard: .set("spark.modify.acls", "*")
_PROG_WILDCARD = re.compile(
    r"""\.(?:set(?:IfMissing)?|config)\s*\(\s*['"]spark\.(?:modify|admin)\.acls['"]"""
    r"""\s*,\s*['"](?P<val>\*)['"]\s*\)"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        elif (
            ch == "/"
            and i + 1 < len(line)
            and line[i + 1] == "/"
            and not in_s
            and not in_d
        ):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        # 1+2: spark.[ui.]acls.enable falsy
        for m in _CONF_ACLS_ENABLE.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: {m.group('key')} disabled "
                    f"(CWE-284/CWE-306, Spark Web UI unrestricted): "
                    f"{raw.strip()[:160]}"
                )

        # 3+4: wildcard acls
        for m in _CONF_ACLS_WILDCARD.finditer(line):
            findings.append(
                f"{path}:{lineno}: {m.group('key')} wildcard `*` "
                f"(CWE-732, every user can modify/admin Spark jobs): "
                f"{raw.strip()[:160]}"
            )

        # 5: CLI --conf
        for m in _CLI_ACLS.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: --conf disables Spark UI ACLs "
                    f"(CWE-284/CWE-306): {raw.strip()[:160]}"
                )

        # 6: programmatic SparkConf set
        for m in _PROG_ACLS.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: SparkConf.set disables UI ACLs "
                    f"(CWE-284/CWE-306): {raw.strip()[:160]}"
                )
        for m in _PROG_WILDCARD.finditer(line):
            findings.append(
                f"{path}:{lineno}: SparkConf.set wildcard acls `*` "
                f"(CWE-732): {raw.strip()[:160]}"
            )
    return findings


_TARGET_NAMES = (
    "spark-defaults.conf",
    "spark-env.sh",
)
_TARGET_EXTS = (
    ".conf", ".properties", ".yaml", ".yml",
    ".sh", ".bash", ".tpl", ".tf",
    ".py", ".scala", ".java",
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
