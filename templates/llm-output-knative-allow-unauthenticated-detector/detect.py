#!/usr/bin/env python3
"""
llm-output-knative-allow-unauthenticated-detector

Flags Knative Serving manifests / install scripts that grant the
``system:unauthenticated`` group (or ``--allow-unauthenticated``)
the right to invoke Knative services. This is the value used in
nearly every Knative quickstart, and the one operators forget to
remove before exposing a cluster to the public internet.

Concrete forms (each requires Knative context in-file):

1. RBAC binding subjects:
       kind: Group
       name: system:unauthenticated
   bound to a Role/ClusterRole that grants
   ``serving.knative.dev/*`` invoke / get on services.

2. ksvc annotation:
       serving.knative.dev/visibility: cluster-local  -- OK
       (the *bad* form is the inverse: explicitly publishing a
       service AND policy-binding ``system:unauthenticated``.)

3. ``gcloud run deploy ... --allow-unauthenticated`` (Knative-on-GKE
   / Cloud Run for Anthos managed service flavour) -- the ksvc gets
   a ``run.googleapis.com/iam-policy`` granting ``allUsers`` invoker.

4. ``allUsers`` / ``allAuthenticatedUsers`` granted ``run.invoker``
   on a Knative service via ``gcloud ... add-iam-policy-binding``.

Maps to:
  - CWE-862: Missing Authorization
  - CWE-284: Improper Access Control
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A01:2021 Broken Access Control

Heuristic
---------
We require Knative context in the file (any of: ``knative``,
``serving.knative.dev``, ``kservice``, ``ksvc``, ``run.googleapis.com``,
``cloud-run``) so we don't flag unrelated Kubernetes RBAC bindings
that happen to mention ``system:unauthenticated``.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_KN_CONTEXT = re.compile(
    r"""(?im)\b(?:knative|serving\.knative\.dev|kservice|ksvc|"""
    r"""run\.googleapis\.com|cloud-run|cloud_run)\b""",
)

# gcloud run deploy ... --allow-unauthenticated
_GCLOUD_ALLOW_UNAUTH = re.compile(
    r"""gcloud\s+(?:beta\s+|alpha\s+)?run\s+(?:deploy|services\s+update)"""
    r"""[^\n]*--allow-unauthenticated\b""",
    re.IGNORECASE,
)

# gcloud ... add-iam-policy-binding ... --member=allUsers ... --role=...invoker
_GCLOUD_ALLUSERS_INVOKER = re.compile(
    r"""gcloud\s+(?:beta\s+|alpha\s+)?run\s+services\s+"""
    r"""add-iam-policy-binding[^\n]*"""
    r"""--member\s*=\s*['"]?(?:allUsers|allAuthenticatedUsers)['"]?""",
    re.IGNORECASE,
)

# kubectl create clusterrolebinding ... --group=system:unauthenticated
_KUBECTL_BIND_UNAUTH = re.compile(
    r"""kubectl\s+create\s+(?:cluster)?rolebinding[^\n]*"""
    r"""--group\s*=\s*['"]?system:unauthenticated['"]?""",
    re.IGNORECASE,
)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return ""


def _scan_yaml_subjects(path: str, text: str) -> List[str]:
    """
    Walk YAML-ish docs for an RBAC binding whose subjects include
    Group/system:unauthenticated AND whose roleRef points at a
    Knative serving role. We do this with line scanning because
    we want stdlib-only and tolerate non-strict YAML.
    """
    findings: List[str] = []
    lines = text.splitlines()

    # Track per-doc state (split on '^---$').
    docs: List[List[str]] = [[]]
    for ln in lines:
        if ln.strip() == "---":
            docs.append([])
        else:
            docs[-1].append(ln)

    line_offset = 1
    for doc in docs:
        joined = "\n".join(doc)
        is_binding = re.search(
            r"""(?m)^\s*kind:\s*(?:Cluster)?RoleBinding\s*$""", joined,
        )
        roleref_kn = re.search(
            r"""(?ms)roleRef:.*?(?:apiGroup|name):\s*[^\n]*"""
            r"""(?:serving\.knative\.dev|knative)""",
            joined,
        )
        unauth = re.search(
            r"""(?ms)subjects:.*?-\s*kind:\s*Group\s*\n\s*name:\s*"""
            r"""system:unauthenticated\b""",
            joined,
        )
        if is_binding and unauth and (roleref_kn or "knative" in joined.lower()):
            # Find the actual subjects line number for reporting.
            for idx, raw in enumerate(doc):
                if "system:unauthenticated" in raw:
                    findings.append(
                        f"{path}:{line_offset + idx}: knative "
                        f"RoleBinding grants system:unauthenticated "
                        f"-> any unauthenticated caller can invoke "
                        f"the bound Knative service / API "
                        f"(CWE-862/CWE-284/CWE-1188): "
                        f"{raw.strip()[:200]}"
                    )
                    break
        line_offset += len(doc) + 1  # +1 for the '---' line we removed
    return findings


def _join_continuations(lines: List[str]) -> List[tuple]:
    """
    Collapse shell backslash continuations into single logical lines.
    Returns list of (line_no_of_first_line, joined_text).
    """
    out: List[tuple] = []
    buf: List[str] = []
    start_no = 1
    for i, raw in enumerate(lines, start=1):
        if not buf:
            start_no = i
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf.append(stripped[:-1])
            continue
        buf.append(stripped)
        out.append((start_no, " ".join(buf)))
        buf = []
    if buf:
        out.append((start_no, " ".join(buf)))
    return out


def scan(path: str) -> List[str]:
    text = _read(path)
    if not text:
        return []
    if not _KN_CONTEXT.search(text):
        return []

    findings: List[str] = []

    for i, raw in _join_continuations(text.splitlines()):
        if _COMMENT_LINE.match(raw):
            continue
        if _GCLOUD_ALLOW_UNAUTH.search(raw):
            findings.append(
                f"{path}:{i}: knative gcloud run "
                f"--allow-unauthenticated -> Knative service is "
                f"published with allUsers as run.invoker; the "
                f"entire public internet can invoke it without "
                f"credentials (CWE-862/CWE-284): "
                f"{raw.strip()[:200]}"
            )
            continue
        if _GCLOUD_ALLUSERS_INVOKER.search(raw):
            findings.append(
                f"{path}:{i}: knative gcloud add-iam-policy-binding "
                f"--member=allUsers/allAuthenticatedUsers -> grants "
                f"run.invoker on a Knative service to the public "
                f"internet (CWE-862/CWE-732): "
                f"{raw.strip()[:200]}"
            )
            continue
        if _KUBECTL_BIND_UNAUTH.search(raw):
            findings.append(
                f"{path}:{i}: knative kubectl create rolebinding "
                f"--group=system:unauthenticated -> binds an "
                f"unauthenticated principal to a Knative role; any "
                f"caller without a token can act on Knative "
                f"resources (CWE-862/CWE-284): "
                f"{raw.strip()[:200]}"
            )
            continue

    findings.extend(_scan_yaml_subjects(path, text))
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini", ".toml")


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
