#!/usr/bin/env python3
"""
llm-output-jenkins-script-security-disabled-detector

Flags Jenkins configurations that disable the **Script Security**
sandbox / approval system. Jenkins ships with a Groovy sandbox plus
an admin-approval queue ("In-process Script Approval") specifically
because Pipeline / Job DSL / Script Console are arbitrary Groovy
execution surfaces against the controller JVM. Disabling the sandbox
means any user who can edit a Pipeline (or any Job DSL seed job that
processes user-supplied scripts) gets RCE on the Jenkins controller,
which in turn typically holds credentials to the entire CI/CD plane.

When an LLM (or a copy-pasted "fix this Pipeline keeps failing
approval" answer) sets `sandbox: false`, `useScriptSecurity: false`,
or boots Jenkins with
`-Dpermissive-script-security.enabled=true`, the safety net is gone.

Maps to:
- CWE-693: Protection Mechanism Failure.
- CWE-862: Missing Authorization.
- CWE-94 / CWE-95: Improper Control of Generation of Code / Eval
  Injection (Pipeline scripts become un-sandboxed Groovy eval).
- CWE-269: Improper Privilege Management (script runs as the
  controller process, not the requesting user).

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Jenkinsfile, *.groovy, *.jenkinsfile, *.yaml, *.yml, *.xml, *.sh,
*.bash, *.service, Dockerfile, docker-compose.* and JCasC files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `#` / `//`
comment lines):

1. `sandbox: false` or `sandbox false` inside a Pipeline `script {}`
   block context (Jenkinsfile / declarative pipeline / JCasC).
2. `useScriptSecurity(false)` / `useScriptSecurity: false` in Job DSL.
3. JVM flag `-Dpermissive-script-security.enabled=true` on a
   `java`/`jenkins.war` invocation, in a systemd unit, Dockerfile
   ENV/CMD, or k8s args.
4. JCasC `security: { scriptApproval: { approvedSignatures: ["*"] } }`
   wildcard approval (the "approve everything" hack).
5. XML `<useScriptSecurity>false</useScriptSecurity>` in a job
   `config.xml`.

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Pipeline / JCasC / Job DSL: `sandbox: false` (YAML/Groovy map style)
# or `sandbox false` (Groovy DSL style). We require the literal token
# `sandbox` followed by whitespace or `:` and then `false`.
_SANDBOX_FALSE = re.compile(
    r"""(?<![A-Za-z_])sandbox\s*[:=]?\s*false\b"""
)

# Job DSL: useScriptSecurity(false) or useScriptSecurity: false
_USE_SCRIPT_SEC_FALSE = re.compile(
    r"""\buseScriptSecurity\s*[:(=]\s*false\s*\)?"""
)

# JVM flag that turns the entire script-security plugin permissive.
_PERMISSIVE_JVM = re.compile(
    r"""-Dpermissive-script-security\.enabled\s*=\s*true\b"""
)

# Wildcard approval: approvedSignatures contains a literal "*"
# entry. Two forms: inline array `["*"]`, and a YAML block-sequence
# `- "*"` immediately under an `approvedSignatures:` key. We track
# the latter by remembering the last seen key in scan_text().
_WILDCARD_APPROVAL_INLINE = re.compile(
    r"""approvedSignatures\s*[:=]\s*\[[^\]]*["']\*["'][^\]]*\]"""
)
_APPROVED_SIG_KEY = re.compile(
    r"""^\s*approvedSignatures\s*:\s*$"""
)
_YAML_WILDCARD_ITEM = re.compile(
    r"""^\s*-\s*["']\*["']\s*$"""
)

# job config.xml: <useScriptSecurity>false</useScriptSecurity>
_XML_USS_FALSE = re.compile(
    r"""<useScriptSecurity>\s*false\s*</useScriptSecurity>""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_inline_comment(line: str) -> str:
    """Strip trailing `#` or `//` comments outside quotes."""
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        nx = line[i + 1] if i + 1 < len(line) else ""
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        elif ch == "/" and nx == "/" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_approved_sigs = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)

        # Track YAML key context for block-sequence wildcard detection.
        if _APPROVED_SIG_KEY.match(line):
            in_approved_sigs = True
            continue
        if in_approved_sigs:
            if _YAML_WILDCARD_ITEM.match(line):
                findings.append(
                    f"{path}:{lineno}: JCasC approvedSignatures has "
                    f"wildcard '*' item -- equivalent to disabling "
                    f"script approval (CWE-862/CWE-269): "
                    f"{raw.strip()[:160]}"
                )
                in_approved_sigs = False
                continue
            # Stop tracking once we leave the list (non-list, non-blank line).
            stripped = line.strip()
            if stripped and not stripped.startswith("-"):
                in_approved_sigs = False
            # fall through to other checks

        if _PERMISSIVE_JVM.search(line):
            findings.append(
                f"{path}:{lineno}: JVM flag "
                f"-Dpermissive-script-security.enabled=true disables "
                f"Jenkins script-security plugin globally "
                f"(CWE-693/CWE-94): {raw.strip()[:160]}"
            )
            continue
        if _WILDCARD_APPROVAL_INLINE.search(line):
            findings.append(
                f"{path}:{lineno}: JCasC approvedSignatures contains "
                f"wildcard '*' -- equivalent to disabling script "
                f"approval (CWE-862/CWE-269): {raw.strip()[:160]}"
            )
            continue
        if _XML_USS_FALSE.search(line):
            findings.append(
                f"{path}:{lineno}: job config.xml sets "
                f"<useScriptSecurity>false</useScriptSecurity> "
                f"(CWE-693/CWE-94): {raw.strip()[:160]}"
            )
            continue
        if _USE_SCRIPT_SEC_FALSE.search(line):
            findings.append(
                f"{path}:{lineno}: Job DSL useScriptSecurity(false) "
                f"opts the seed job out of sandboxing "
                f"(CWE-693/CWE-94): {raw.strip()[:160]}"
            )
            continue
        if _SANDBOX_FALSE.search(line):
            findings.append(
                f"{path}:{lineno}: Pipeline/JCasC `sandbox: false` "
                f"runs Groovy un-sandboxed against the controller JVM "
                f"(CWE-693/CWE-94/CWE-269): {raw.strip()[:160]}"
            )
            continue
    return findings


_TARGET_NAMES = (
    "jenkinsfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "config.xml",
)
_TARGET_EXTS = (
    ".groovy", ".jenkinsfile", ".yaml", ".yml", ".xml",
    ".sh", ".bash", ".service", ".tpl", ".env",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile") \
                            or low.startswith("jenkinsfile"):
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
