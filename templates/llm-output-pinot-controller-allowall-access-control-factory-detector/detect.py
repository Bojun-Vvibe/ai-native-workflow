#!/usr/bin/env python3
"""
llm-output-pinot-controller-allowall-access-control-factory-detector

Flags Apache Pinot controller / broker configurations that wire
the access-control factory to the ``AllowAllAccessControlFactory``
implementation -- the upstream "no checks at all" stub that
ships with Pinot for development and is repeatedly emitted by
LLMs as a "make auth work" answer.

Upstream:
  - apache/pinot: https://github.com/apache/pinot
  - Source of the stub:
    pinot-controller/src/main/java/org/apache/pinot/controller/
      api/access/AllowAllAccessControlFactory.java
  - Pinot security doc:
    https://docs.pinot.apache.org/operators/tutorials/authentication
  - Verified against Pinot 1.0.0 .. 1.2.x where the
    ``AllowAllAccessControlFactory`` class is still the default
    when ``controller.admin.access.control.factory.class`` is
    unset *and* is the documented "open" option.

Concrete forms detected (each requires Pinot context in-file):

1. ``controller.admin.access.control.factory.class =
    org.apache.pinot.controller.api.access.AllowAllAccessControlFactory``
2. ``pinot.broker.access.control.class =
    org.apache.pinot.broker.broker.AllowAllAccessControlFactory``
3. Helm / k8s values: ``accessControlFactory: AllowAll`` under a
   Pinot chart / Pinot context.
4. JVM flag ``-Dcontroller.admin.access.control.factory.class=
    ...AllowAllAccessControlFactory`` in start scripts.

Why this is dangerous
---------------------
Pinot's controller exposes the cluster admin REST surface
(``/tables``, ``/segments``, ``/schemas``, ``/instances``,
``/tenants``, ``/tasks``). With ``AllowAllAccessControlFactory``
every endpoint returns "authorized" without consulting any
credential. Any unauthenticated network reachability becomes:

- arbitrary table / schema deletion -> data loss;
- arbitrary segment upload -> data poisoning of every Pinot
  query that reads the table;
- task scheduling (``MinionTask``) of attacker-defined task
  classes -> remote code execution on minion workers;
- exfiltration of segment data via download endpoints.

The class is named, source-visible, and documented as a
development-only stub; shipping it to production removes the
authentication boundary on the cluster admin plane.

Maps to:
  - CWE-284: Improper Access Control
  - CWE-285: Improper Authorization
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - OWASP A01:2021 Broken Access Control
  - OWASP A05:2021 Security Misconfiguration

Heuristic
---------
We require Pinot context (any of: ``pinot``, ``apache.pinot``,
``org.apache.pinot``, ``pinot-controller``, ``pinot-broker``).

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_PINOT_CONTEXT = re.compile(
    r"""(?im)\b(?:pinot|apache\.pinot|org\.apache\.pinot|"""
    r"""pinot-controller|pinot-broker|pinot-server)\b""",
)

# .properties / config style:
#   controller.admin.access.control.factory.class = ...AllowAllAccessControlFactory
#   pinot.broker.access.control.class            = ...AllowAllAccessControlFactory
_PROP_ALLOWALL = re.compile(
    r"""(?im)^\s*(?:controller\.admin\.access\.control\.factory\.class|"""
    r"""pinot\.broker\.access\.control\.class|"""
    r"""access\.control\.factory\.class)\s*[:=]\s*"""
    r"""(?:['"])?([^\s'"#]+AllowAllAccessControlFactory)['"]?\s*(?:#.*)?$""",
)

# YAML / Helm form:
#   accessControlFactory: AllowAll
#   accessControl:
#     factory: AllowAllAccessControlFactory
_YAML_ALLOWALL_KEY = re.compile(
    r"""(?im)^\s*(?:accessControlFactory|accessControl\.factory|factory)\s*:\s*"""
    r"""['"]?(AllowAll(?:AccessControlFactory)?)['"]?\s*(?:#.*)?$""",
)

# JVM start-script flag:
#   -Dcontroller.admin.access.control.factory.class=...AllowAllAccessControlFactory
_JVM_ALLOWALL = re.compile(
    r"""-D(?:controller\.admin\.access\.control\.factory\.class|"""
    r"""pinot\.broker\.access\.control\.class)\s*=\s*"""
    r"""(\S*AllowAllAccessControlFactory)""",
)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return ""


def scan(path: str) -> List[str]:
    text = _read(path)
    if not text:
        return []
    if not _PINOT_CONTEXT.search(text):
        return []

    findings: List[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        for rx in (_PROP_ALLOWALL, _YAML_ALLOWALL_KEY, _JVM_ALLOWALL):
            m = rx.search(raw)
            if m:
                findings.append(
                    f"{path}:{i}: pinot access-control factory "
                    f"wired to AllowAllAccessControlFactory "
                    f"('{m.group(1)}') -> the controller / broker "
                    f"REST admin surface returns 'authorized' for "
                    f"every unauthenticated request: arbitrary "
                    f"table/schema deletion, segment upload "
                    f"poisoning, MinionTask scheduling (RCE on "
                    f"minion workers), and segment exfiltration "
                    f"are all reachable without credentials "
                    f"(CWE-284/CWE-285/CWE-306/CWE-1188/CWE-732): "
                    f"{raw.strip()[:200]}"
                )
                break
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini", ".toml",
                ".env")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.startswith("dockerfile") or \
                            low.startswith("docker-compose") or \
                            low.endswith(_TARGET_EXTS):
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
