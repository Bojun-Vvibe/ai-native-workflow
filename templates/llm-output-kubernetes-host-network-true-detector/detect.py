#!/usr/bin/env python3
"""
llm-output-kubernetes-host-network-true-detector

Flags Kubernetes workload manifests (Pod, Deployment, StatefulSet,
DaemonSet, Job, CronJob, ReplicaSet, ReplicationController, PodTemplate)
where ``hostNetwork: true`` is set on the Pod spec.

A pod with ``hostNetwork: true`` shares the host's network namespace.
That defeats Kubernetes network isolation entirely: the pod can bind
on host ports, sniff traffic on host interfaces, reach localhost-only
services on the node (kubelet, etcd peer ports, node-local cache,
metadata services), and bypass NetworkPolicy because NetworkPolicy
operates on the pod network namespace it no longer uses.

Maps to CWE-668 (Exposure of Resource to Wrong Sphere) and the CIS
Kubernetes Benchmark control 5.2.4 (Minimize the admission of
containers wishing to share the host network namespace).

LLMs reach for ``hostNetwork: true`` because it is the fastest way to
make "connection refused to 127.0.0.1" or "cannot bind low port" go
away when a user pastes an error and asks for a fix. Almost every
legitimate use (DNS, CNI agents, metrics exporters that genuinely
need host visibility) is operator-installed and not what an LLM
should be emitting from a casual prompt.

Stdlib only. Reads files from argv (or recurses into directories for
``*.yaml`` / ``*.yml``). Exit 0 = no findings, 1 = finding(s),
2 = usage error.

Per-line suppression marker:

    hostNetwork: true  # llm-allow:host-network
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

SUPPRESS = "llm-allow:host-network"

# hostNetwork: true / True / yes / on, optional trailing comment.
_LINE_RE = re.compile(
    r"^(\s*)hostNetwork\s*:\s*(?:true|True|yes|on)\s*(?:#.*)?$"
)

# Require a recognizable workload kind somewhere in the document so we
# don't flag unrelated YAML that happens to use the field name.
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
            f"{path}:{i}: host-network-true: {line.rstrip()}"
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
