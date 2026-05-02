#!/usr/bin/env python3
"""
llm-output-kubernetes-privileged-pod-detector

Flags Kubernetes workload manifests (Pod, Deployment, StatefulSet,
DaemonSet, Job, CronJob, ReplicaSet, ReplicationController, PodTemplate)
where a container's ``securityContext.privileged`` is set to true.

A privileged container effectively runs as root on the node: all
Linux capabilities granted, default seccomp/AppArmor profile dropped,
and host devices visible. From there, container escape to the node
is trivial via well-known techniques. Maps to CWE-250, CWE-269, and
CIS Kubernetes Benchmark control 5.2.1.

LLMs reach for ``privileged: true`` because it makes a permission
error disappear without requiring the model to reason about which
specific capability or mount the workload actually needed.

Stdlib only. Reads files from argv (or recurses into directories for
``*.yaml`` / ``*.yml``). Exit 0 = no findings, 1 = finding(s),
2 = usage error.

Per-line suppression marker:

    privileged: true  # llm-allow:privileged-pod
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

SUPPRESS = "llm-allow:privileged-pod"

# privileged: true / True / yes / on, optional trailing comment.
# Anchored so we don't match e.g. `allowPrivilegeEscalation`.
_LINE_RE = re.compile(
    r"^(\s*)privileged\s*:\s*(?:true|True|yes|on)\s*(?:#.*)?$"
)

# Require a recognizable workload kind somewhere in the document so
# we don't flag e.g. PodSecurityPolicy descriptors or unrelated YAML
# that uses the word "privileged" as a string value.
_KIND_RE = re.compile(
    r"^\s*kind\s*:\s*"
    r"(?:Pod|Deployment|StatefulSet|DaemonSet|Job|CronJob"
    r"|ReplicaSet|ReplicationController|PodTemplate)"
    r"\s*(?:#.*)?$",
    re.MULTILINE,
)


def scan_text(text: str, path: str) -> List[str]:
    if not _KIND_RE.search(text):
        return []
    findings: List[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not _LINE_RE.match(line):
            continue
        if SUPPRESS in line:
            continue
        findings.append(
            f"{path}:{i}: privileged-pod: {line.rstrip()}"
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
