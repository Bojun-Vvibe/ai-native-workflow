#!/usr/bin/env python3
"""
llm-output-k8s-pod-privileged-true-detector

Flags Kubernetes manifests (Pod, Deployment, StatefulSet, DaemonSet,
Job, CronJob, ReplicaSet, ReplicationController) where a container
runs with `securityContext.privileged: true`. A privileged container
shares the host kernel's namespaces and capability set, defeating the
container boundary entirely (CWE-250: Execution with Unnecessary
Privileges; CIS Kubernetes Benchmark 5.2.1).

LLMs reach for `privileged: true` because it's the fastest way to
make "permission denied" errors disappear when the user pastes a
container error and asks the model to fix it.

Stdlib only. Reads files passed on argv (or recurses into directories
for *.yaml / *.yml). Exit 0 = no findings, 1 = finding(s),
2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Look for `privileged: true` (case-insensitive on the bool value)
# inside something that smells like a securityContext block. We don't
# parse YAML — we want zero deps, and the false-positive surface is
# tiny because the literal `privileged: true` rarely appears in
# non-k8s YAML.
_LINE_RE = re.compile(
    r"^\s*privileged\s*:\s*(?:true|True|yes|on)\s*(?:#.*)?$"
)

# Skip files that obviously aren't k8s manifests. We require at least
# one of these top-level kinds to appear somewhere in the file.
_KIND_RE = re.compile(
    r"^\s*kind\s*:\s*"
    r"(?:Pod|Deployment|StatefulSet|DaemonSet|Job|CronJob|ReplicaSet|ReplicationController)"
    r"\s*(?:#.*)?$",
    re.MULTILINE,
)


def scan_text(text: str, path: str) -> List[str]:
    if not _KIND_RE.search(text):
        return []
    findings: List[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _LINE_RE.match(line):
            findings.append(
                f"{path}:{i}: container running with privileged=true "
                f"(CWE-250 / CIS K8s 5.2.1): {line.strip()}"
            )
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    exts = (".yaml", ".yml", ".yaml.txt", ".yml.txt")
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(exts):
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
