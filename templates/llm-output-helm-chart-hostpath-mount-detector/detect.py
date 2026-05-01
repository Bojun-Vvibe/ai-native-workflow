#!/usr/bin/env python3
"""
llm-output-helm-chart-hostpath-mount-detector

Flags Helm chart templates (or raw Kubernetes manifests) that mount a
node directory into a Pod via `hostPath`. This is the documented Kubernetes
anti-pattern and maps to CWE-732 (Incorrect Permission Assignment for
Critical Resource): a hostPath volume gives the workload read or write
access to a path on the underlying node's filesystem, breaking the pod
isolation boundary. Mounting paths like `/`, `/etc`, `/var/run/docker.sock`
or `/var/lib/kubelet` is effectively a node takeover primitive.

LLMs reach for `hostPath` because it is the shortest way to "share state
with the node" or "read host logs", and Helm-charted manifests slip past
review because the dangerous bit is buried inside `values.yaml`-driven
indentation.

Stdlib-only. Reads files passed on argv (or recurses into dirs and picks
files matching `*.yaml`, `*.yml`, or anything under `templates/`).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.

Heuristic
---------
For each YAML-ish line we walk we look for two shapes:

1. A volume entry with a `hostPath:` key, optionally followed (within a
   small window) by a `path:` value. Helm templating chunks like
   `{{ .Values.foo }}` are still flagged -- the whole point is the
   chart is *capable* of mounting a host path.
2. A bare `path:` immediately under a `hostPath:` block (Helm authors
   sometimes split across lines or interpolate `path` from values).

We do NOT try to parse YAML (Helm output is rarely valid YAML before
rendering). We do a line-window scan that tolerates:
  - leading whitespace / list dashes
  - Helm `{{ ... }}` tokens
  - inline comments (`#`)
  - multi-document streams separated by `---`

We always emit findings as `path:line: ...` so tooling can jump to them.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Match `hostPath:` as a YAML key (start of mapping value) at any
# indentation. We ignore the trailing value because hostPath sometimes
# appears as `hostPath:` followed by an indented `path:` block.
_HOSTPATH_KEY = re.compile(r"^\s*(?:-\s+)?hostPath\s*:\s*(?:#.*)?$")

# Same key but *with* an inline mapping like `hostPath: {path: /etc}`.
_HOSTPATH_INLINE = re.compile(r"^\s*(?:-\s+)?hostPath\s*:\s*\{[^}]*path\s*:")

# Within a hostPath block, look for `path: <value>`. We treat any value
# that starts with `/` or `{{` (Helm) as a real mount path.
_PATH_LINE = re.compile(
    r"^\s*path\s*:\s*[\"']?(?P<val>(/[^\s\"'#]*|\{\{[^}]+\}\}[^\s\"'#]*))"
)

# Comment / blank-line skip
_BLANK_OR_COMMENT = re.compile(r"^\s*(#.*)?$")

# Sensitive path prefixes -- if matched, we annotate the finding more loudly.
# These are well-known node-takeover primitives.
_SENSITIVE_PREFIXES = (
    "/",                    # root
    "/etc",
    "/var/run/docker.sock",
    "/var/run",
    "/var/lib/kubelet",
    "/var/lib/docker",
    "/proc",
    "/sys",
    "/root",
    "/home",
    "/dev",
)


def _is_sensitive(p: str) -> bool:
    # Helm-templated values we cannot evaluate: treat as sensitive (an LLM
    # author can wire any path through values.yaml).
    if p.startswith("{{"):
        return True
    if p == "/":
        return True
    for prefix in _SENSITIVE_PREFIXES:
        if prefix == "/":
            continue
        if p == prefix or p.startswith(prefix + "/"):
            return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]

        # Inline form: `hostPath: { path: /foo }`
        if _HOSTPATH_INLINE.match(line):
            m = re.search(r"path\s*:\s*[\"']?([^\s,}\"']+)", line)
            mount = m.group(1) if m else "<unknown>"
            sev = "SENSITIVE" if _is_sensitive(mount) else "hostPath"
            findings.append(
                f"{path}:{i+1}: hostPath volume mount (CWE-732, "
                f"breaks pod-host isolation): {sev} path={mount}"
            )
            i += 1
            continue

        # Block form: `hostPath:` followed by indented children including `path:`
        if _HOSTPATH_KEY.match(line):
            host_lineno = i + 1
            # Look ahead up to 8 non-blank lines for an aligned `path:` child.
            j = i + 1
            scanned = 0
            mount = None
            mount_line = host_lineno
            while j < n and scanned < 12:
                child = lines[j]
                if _BLANK_OR_COMMENT.match(child):
                    j += 1
                    continue
                # Stop if we dedent back to or past the hostPath indent --
                # then we're out of this mapping.
                child_indent = len(child) - len(child.lstrip())
                host_indent = len(line) - len(line.lstrip())
                if child_indent <= host_indent and not child.lstrip().startswith("-"):
                    break
                m = _PATH_LINE.match(child)
                if m:
                    mount = m.group("val")
                    mount_line = j + 1
                    break
                j += 1
                scanned += 1
            if mount is None:
                # hostPath: declared with no resolvable path -- still flag,
                # because the whole hostPath surface is the hazard.
                findings.append(
                    f"{path}:{host_lineno}: hostPath volume declared "
                    f"(CWE-732, breaks pod-host isolation): path=<unresolved>"
                )
            else:
                sev = "SENSITIVE" if _is_sensitive(mount) else "hostPath"
                findings.append(
                    f"{path}:{mount_line}: hostPath volume mount "
                    f"(CWE-732, breaks pod-host isolation): {sev} path={mount}"
                )
            i = max(i + 1, j)
            continue

        i += 1
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.endswith(".yaml") or low.endswith(".yml") or low.endswith(".tpl"):
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
