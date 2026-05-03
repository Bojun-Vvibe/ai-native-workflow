#!/usr/bin/env python3
"""Detect GitLab Runner configuration that grants jobs ``privileged``
container mode.

In ``config.toml``, a ``[runners.docker]`` or ``[runners.kubernetes]``
block with ``privileged = true`` causes every CI job to launch with
``--privileged``: full ``/dev`` access, ability to mount host
filesystems, load kernel modules, run nested docker against the host
socket, etc. On a shared / multi-tenant runner this is a one-line
container escape primitive.

This detector also flags:

  * Helm-style ``runners.privileged: true`` in the GitLab Runner
    Helm chart values.
  * ``privileged: true`` nested inside a ``kubernetes:`` map in
    runner YAML.
  * ``--docker-privileged`` on ``gitlab-runner register`` command
    lines.

A file containing the comment marker
``gitlab-runner-privileged-allowed`` is treated as suppressed.
"""

from __future__ import annotations

import os
import re
import sys

SUPPRESS_MARK = "gitlab-runner-privileged-allowed"

TRUTHY = {"true", "1", "yes", "on"}

# Match a [runners.docker] or [runners.kubernetes] section header,
# then look for `privileged = <truthy>` until the next [section].
TOML_SECTION = re.compile(
    r"""(?ms)
    ^[ \t]*\[runners\.(docker|kubernetes)\][ \t]*\n
    (.*?)
    (?=^[ \t]*\[|\Z)
    """,
    re.VERBOSE,
)

TOML_PRIV = re.compile(
    r"""^[ \t]*privileged[ \t]*=[ \t]*([A-Za-z0-9_"']+)""",
    re.MULTILINE,
)

# Helm chart top-level: `runners:` map, then `privileged: true`.
HELM_RUNNERS_BLOCK = re.compile(
    r"""(?ms)^[ \t]*runners[ \t]*:\s*\n((?:[ \t]+.*\n)+)""",
)
HELM_PRIV_INNER = re.compile(
    r"""^[ \t]+privileged[ \t]*:[ \t]*([A-Za-z0-9_"']+)""",
    re.MULTILINE,
)
HELM_PRIV_FLAT = re.compile(
    r"""^[ \t]*runners\.privileged[ \t]*:[ \t]*([A-Za-z0-9_"']+)""",
    re.MULTILINE,
)

# `kubernetes:` block with nested `privileged: true`.
K8S_BLOCK = re.compile(
    r"""(?ms)^[ \t]*kubernetes[ \t]*:\s*\n((?:[ \t]+.*\n)+)""",
)

# `gitlab-runner register ... --docker-privileged ...` in shell
# scripts. The register command often spans many lines via `\` line
# continuations, so we test for the flag in the same logical region
# as a `register` invocation rather than on the same physical line.
REGISTER_INVOKE = re.compile(
    r"""gitlab-runner\s+register\b""",
    re.IGNORECASE,
)
REGISTER_FLAG = re.compile(
    r"""--docker-privileged(?:\s|=|$|\\)""",
    re.IGNORECASE,
)


def _is_truthy(val: str) -> bool:
    return val.strip().strip('"').strip("'").lower() in TRUTHY


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []
    seen: set[tuple] = set()

    # config.toml [runners.docker] / [runners.kubernetes]
    for sec in TOML_SECTION.finditer(text):
        flavor = sec.group(1)
        body = sec.group(2)
        for m in TOML_PRIV.finditer(body):
            if _is_truthy(m.group(1)):
                key = ("toml", flavor)
                if key not in seen:
                    findings.append(
                        f"{path}: [runners.{flavor}] privileged = true — "
                        f"every CI job runs with full host access; on a "
                        f"shared runner this is a one-line container escape"
                    )
                    seen.add(key)

    # Helm flat: runners.privileged: true
    for m in HELM_PRIV_FLAT.finditer(text):
        if _is_truthy(m.group(1)):
            key = ("helm-flat",)
            if key not in seen:
                findings.append(
                    f"{path}: runners.privileged: true (Helm values) — "
                    f"runner pods will launch every job with "
                    f"securityContext.privileged: true"
                )
                seen.add(key)

    # Helm nested: runners: \n  privileged: true
    for block in HELM_RUNNERS_BLOCK.finditer(text):
        body = block.group(1)
        for m in HELM_PRIV_INNER.finditer(body):
            if _is_truthy(m.group(1)):
                key = ("helm-nested",)
                if key not in seen:
                    findings.append(
                        f"{path}: runners.privileged (nested Helm value) is "
                        f"true — runner pods will launch every job "
                        f"privileged"
                    )
                    seen.add(key)

    # Nested kubernetes: \n  privileged: true
    for block in K8S_BLOCK.finditer(text):
        body = block.group(1)
        for m in HELM_PRIV_INNER.finditer(body):
            if _is_truthy(m.group(1)):
                key = ("k8s-nested",)
                if key not in seen:
                    findings.append(
                        f"{path}: kubernetes.privileged: true — pod will "
                        f"run with full host capabilities"
                    )
                    seen.add(key)

    # gitlab-runner register --docker-privileged (possibly across
    # backslash-continued lines).
    if REGISTER_INVOKE.search(text) and REGISTER_FLAG.search(text):
        key = ("register",)
        if key not in seen:
            findings.append(
                f"{path}: `gitlab-runner register --docker-privileged` — "
                f"the registered runner will launch every job privileged"
            )
            seen.add(key)

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [file ...]", file=sys.stderr)
        return 2
    files: list[str] = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                for name in names:
                    files.append(os.path.join(root, name))
        else:
            files.append(arg)

    total = 0
    for f in files:
        for finding in scan_file(f):
            print(finding)
            total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
