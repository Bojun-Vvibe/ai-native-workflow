#!/usr/bin/env python3
"""
llm-output-milvus-common-security-authorizationenabled-false-detector

Flags Milvus vector-database deployments that leave
`common.security.authorizationEnabled` at its upstream default of
`false`, OR explicitly set it to `false`. With authorization off,
every Milvus gRPC / restful endpoint is unauthenticated: any
caller who can reach port 19530 (gRPC) or 9091 (metrics) can
create, read, mutate, and drop every collection in the cluster.

Why LLMs reach for this
-----------------------
The upstream `milvus.yaml` shipped in `milvus-io/milvus` has, for
many releases:

    common:
      security:
        authorizationEnabled: false

and the official quickstart docker-compose plus the Helm chart
both inherit that default. LLMs producing "deploy Milvus" snippets
copy the upstream block verbatim or simply omit the security
section, and the operator deploys it on a host that is reachable
from outside the cluster (Kubernetes `LoadBalancer`, public VPS,
exposed Docker port).

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.

Heuristic
---------
We flag, outside `#` / `//` comments:

1. YAML key form: a line ending in `authorizationEnabled: false`
   (or `False`, `0`, `no`, `off`) that lives under a
   `common:` -> `security:` block, OR is present at any nesting
   level (Helm values often flatten).
2. Helm CLI form: `--set common.security.authorizationEnabled=false`
   or `--set ...authorizationEnabled=false`.
3. Env-var override used by the Milvus image:
   `MILVUS_COMMON_SECURITY_AUTHORIZATIONENABLED=false`
   (or `…_AUTHORIZATION_ENABLED=false`, both are accepted by
   the image entrypoint).
4. Python SDK / pymilvus connect calls that pass
   `secure=False` AND no `user=`/`token=` argument — these are
   NOT flagged here (out of scope), but the README points users
   at the corresponding pymilvus-no-credentials detector.

We DO NOT flag a file that, anywhere outside a comment, sets
`authorizationEnabled` to a truthy value (`true`, `1`, `yes`, `on`)
— that means the operator overrode the default upward.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks *.yml, *.yaml, *.env, .env*, *.sh, *.bash, Dockerfile,
docker-compose*, *.tf, *.conf, *.tpl).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_FALSY = {"false", "0", "no", "off"}
_TRUTHY = {"true", "1", "yes", "on"}

# YAML / values form: any line `authorizationEnabled: <val>`.
_YAML = re.compile(
    r"""^\s*authorizationEnabled\s*:\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?\s*$"""
)

# Helm --set form.
_HELM = re.compile(
    r"""--set\s+(?:[A-Za-z0-9_.\-\\]+\.)?authorizationEnabled\s*=\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?""",
    re.IGNORECASE,
)

# Env-var override (image entrypoint accepts either spelling).
_ENV = re.compile(
    r"""\bMILVUS_COMMON_SECURITY_AUTHORIZATION_?ENABLED\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
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


def _has_truthy_override(text: str) -> bool:
    """Return True if any non-comment line sets authorizationEnabled
    to a truthy value. We use that as a signal that the operator
    explicitly enabled auth somewhere in the file."""
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        for pat in (_YAML, _HELM, _ENV):
            for m in pat.finditer(line):
                if m.group("val").lower() in _TRUTHY:
                    return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    if _has_truthy_override(text):
        return []
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        m = _YAML.match(line)
        if m and m.group("val").lower() in _FALSY:
            findings.append(
                f"{path}:{lineno}: authorizationEnabled="
                f"'{m.group('val')}' (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        for m in _HELM.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: helm --set authorizationEnabled="
                    f"'{m.group('val')}' (CWE-306/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )

        for m in _ENV.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: MILVUS_COMMON_SECURITY_"
                    f"AUTHORIZATION[_]ENABLED='{m.group('val')}' "
                    f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
                )

    return findings


_TARGET_NAMES = (
    "milvus.yaml", "milvus.yml", "dockerfile", ".env",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".env", ".sh", ".bash", ".tf", ".conf", ".tpl",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.endswith(_TARGET_EXTS) or low.startswith(".env"):
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
